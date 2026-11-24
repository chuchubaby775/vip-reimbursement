"""Exercise deployment safeguards using fake CLIs; never contact a cluster."""
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'ack-deploy.sh'
FAKE_CLI = '''#!/usr/bin/env python3
import json, os, pathlib, stat, sys
tool = pathlib.Path(sys.argv[0]).name
config = pathlib.Path(os.environ['KUBECONFIG'])
assert config.is_file() and stat.S_IMODE(config.stat().st_mode) == 0o600
with open(os.environ['ACK_TEST_LOG'], 'a') as handle:
    handle.write(json.dumps({'tool': tool, 'args': sys.argv[1:], 'config': str(config)}) + '\\n')
if tool == 'kubectl':
    if 'pvc' in sys.argv:
        print(os.environ.get('ACK_TEST_PVC_PHASE', 'Bound'), end='')
    elif any(arg.startswith('go-template=') for arg in sys.argv):
        print(os.environ.get('ACK_TEST_SECRET_KEYS', 'ok'), end='')
    else:
        print('ok')
elif tool == 'helm':
    sys.exit(int(os.environ.get('ACK_TEST_HELM_EXIT', '0')))
'''


class AckDeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ack-script-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for name in ('kubectl', 'helm'):
            path = self.bin / name
            path.write_text(FAKE_CLI)
            path.chmod(0o700)
        self.config = self.root / 'kube-base64'
        self.config.write_bytes(base64.b64encode(b'apiVersion: v1\nkind: Config\n'))
        self.log = self.root / 'calls.jsonl'
        # Do not inherit any real deployment variables or kubeconfig.
        self.env = {
            'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
            'TMPDIR': str(self.root), 'ACK_TEST_LOG': str(self.log),
            'DEPLOY_ACK_NAME': 'synthetic-context',
            'DEPLOY_NAMESPACE': 'vip-synthetic', 'DEPLOY_NAME': 'vip-test',
            'PUBLIC_HOST': 'vip.synthetic.test', 'INGRESS_CLASS': 'test-ingress',
            'DATA_PVC_NAME': 'test-data', 'APP_SECRET_NAME': 'test-secret',
            'IMAGE_PULL_SECRET_NAME': 'test-registry',
            'ACK_KUBE_CONFIG_BASE64': str(self.config),
            'CI_REGISTRY_IMAGE': 'registry.synthetic.test/team/vip',
            'CI_COMMIT_SHA': 'a' * 40, 'CI_COMMIT_BRANCH': 'main',
            'CI_DEFAULT_BRANCH': 'main', 'PUBLIC_ACCESS_CONFIRMED': '1',
            'TLS_SECRET_NAME': 'test-tls',
        }

    def run_script(self, **changes):
        result = subprocess.run(['sh', str(SCRIPT)], env={**self.env, **changes},
                                cwd=SCRIPT.parents[1], capture_output=True, text=True,
                                timeout=15)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        for call in calls:
            self.assertFalse(Path(call['config']).exists(), 'Temporary kubeconfig must be removed')
        return result, calls

    def test_manual_job_uses_assigned_context_storage_and_commit(self):
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        helm = next(c for c in calls if c['tool'] == 'helm')
        args = helm['args']
        for expected in ('--atomic', '--wait', 'persistence.existingClaim=test-data',
                         'secrets.existingSecret=test-secret',
                         'image.tag=vip-' + 'a' * 40,
                         'ingress.tlsSecretName=test-tls'):
            self.assertIn(expected, args)
        self.assertEqual(args[args.index('--kube-context') + 1], 'synthetic-context')
        self.assertTrue(all('--context' in c['args'] for c in calls if c['tool'] == 'kubectl'))
        self.assertNotIn('apiVersion', result.stdout + result.stderr)

    def test_missing_assignment_stops_before_any_cluster_access(self):
        result, calls = self.run_script(DEPLOY_NAMESPACE='')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_shared_example_namespace_is_rejected(self):
        result, calls = self.run_script(DEPLOY_NAMESPACE='examples')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_feature_branch_cannot_deploy(self):
        result, calls = self.run_script(CI_COMMIT_BRANCH='codex/test')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_https_and_proxy_confirmation_required(self):
        for changes in ({'PUBLIC_ACCESS_CONFIRMED': '0'},
                        {'TLS_MODE': 'gateway'},
                        {'TRUST_PROXY_HEADERS': '1'}):
            with self.subTest(changes=changes):
                result, calls = self.run_script(**changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])

    def test_helm_value_injection_is_rejected(self):
        result, calls = self.run_script(DATA_PVC_NAME='safe,replicaCount=2')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_plain_ci_variable_is_not_a_kubeconfig_file(self):
        result, calls = self.run_script(ACK_KUBE_CONFIG_BASE64='not-a-file')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_missing_application_keys_prevents_helm(self):
        result, calls = self.run_script(ACK_TEST_SECRET_KEYS='')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c['tool'] == 'helm' for c in calls))

    def test_wait_for_consumer_storage_can_bind_during_install(self):
        result, calls = self.run_script(ACK_TEST_PVC_PHASE='Pending')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c['tool'] == 'helm' for c in calls))

    def test_failed_helm_cleans_credentials_and_skips_success(self):
        result, calls = self.run_script(ACK_TEST_HELM_EXIT='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Deployment is ready', result.stdout)
        self.assertFalse(any('rollout' in c['args'] for c in calls))


if __name__ == '__main__':
    unittest.main()

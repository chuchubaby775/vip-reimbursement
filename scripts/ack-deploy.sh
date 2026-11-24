#!/bin/sh
# Run only inside the company's protected, manual staging CI job.
set -eu

: "${DEPLOY_ACK_NAME:?IT must assign the kubeconfig context}"
: "${DEPLOY_NAMESPACE:?IT must assign a namespace}"
: "${DEPLOY_NAME:?Release name is required}"
: "${PUBLIC_HOST:?IT must assign a public HTTPS domain}"
: "${INGRESS_CLASS:?IT must assign an IngressClass}"
: "${DATA_PVC_NAME:?IT must supply an existing persistent claim}"
: "${APP_SECRET_NAME:?IT must supply an existing application Secret}"
: "${IMAGE_PULL_SECRET_NAME:?IT must supply a registry pull Secret}"
: "${ACK_KUBE_CONFIG_BASE64:?IT must configure a File type CI variable}"
: "${CI_REGISTRY_IMAGE:?GitLab registry is required}"
: "${CI_COMMIT_SHA:?A GitLab commit is required}"
: "${CI_COMMIT_BRANCH:?Deployment must run from a branch}"
: "${CI_DEFAULT_BRANCH:?GitLab default branch is required}"

fail() { printf '%s\n' "$1" >&2; exit 1; }
dns_label() {
    printf '%s' "$2" | LC_ALL=C grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$' || fail "Invalid name: $1"
    [ "${#2}" -le 63 ] || fail "Name too long: $1"
}
[ "$CI_COMMIT_BRANCH" = "$CI_DEFAULT_BRANCH" ] || fail 'Deploy only from the default branch.'
[ "${PUBLIC_ACCESS_CONFIRMED:-0}" = 1 ] || fail 'IT must confirm public HTTPS, paths, upload size and timeouts; set PUBLIC_ACCESS_CONFIRMED=1.'
[ "$DEPLOY_NAMESPACE" != examples ] || fail 'Use the namespace allocated to the VIP website, not the shared examples namespace.'
dns_label DEPLOY_NAMESPACE "$DEPLOY_NAMESPACE"
dns_label DEPLOY_NAME "$DEPLOY_NAME"
[ "${#DEPLOY_NAME}" -le 53 ] || fail 'Helm release names have a maximum length of 53.'
dns_label INGRESS_CLASS "$INGRESS_CLASS"
dns_label DATA_PVC_NAME "$DATA_PVC_NAME"
dns_label APP_SECRET_NAME "$APP_SECRET_NAME"
dns_label IMAGE_PULL_SECRET_NAME "$IMAGE_PULL_SECRET_NAME"
printf '%s' "$PUBLIC_HOST" | LC_ALL=C grep -Eq '^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]([a-z0-9-]*[a-z0-9])?$' || fail 'PUBLIC_HOST must be a hostname without a scheme or path.'
case "$PUBLIC_HOST" in *.invalid|*.example.com|example.com) fail 'Replace the example domain with the assigned domain.' ;; esac
printf '%s' "$CI_REGISTRY_IMAGE" | LC_ALL=C grep -Eq '^[a-z0-9][a-z0-9./:_-]+$' || fail 'Invalid GitLab registry image path.'
printf '%s' "$CI_COMMIT_SHA" | LC_ALL=C grep -Eq '^[a-f0-9]{40}$' || fail 'Expected a complete Git commit SHA.'

TLS_MODE=${TLS_MODE:-secret}
TLS_SECRET_NAME=${TLS_SECRET_NAME:-}
case "$TLS_MODE" in
  secret) dns_label TLS_SECRET_NAME "$TLS_SECRET_NAME" ;;
  gateway) [ "${GATEWAY_HTTPS_CONFIRMED:-0}" = 1 ] || fail 'IT must confirm gateway TLS and set GATEWAY_HTTPS_CONFIRMED=1.' ;;
  *) fail 'TLS_MODE must be secret or gateway.' ;;
esac
TRUST_PROXY_HEADERS=${TRUST_PROXY_HEADERS:-0}
case "$TRUST_PROXY_HEADERS" in 0|1) ;; *) fail 'TRUST_PROXY_HEADERS must be 0 or 1.' ;; esac
if [ "$TRUST_PROXY_HEADERS" = 1 ]; then
  [ "${PROXY_HEADER_CONFIRMED:-0}" = 1 ] || fail 'IT must confirm X-Real-IP overwrite and restricted backend access; set PROXY_HEADER_CONFIRMED=1.'
fi
HELM_TIMEOUT=${HELM_TIMEOUT:-10m}
printf '%s' "$HELM_TIMEOUT" | LC_ALL=C grep -Eq '^[1-9][0-9]*(s|m)$' || fail 'HELM_TIMEOUT must be seconds or minutes.'
[ -f "$ACK_KUBE_CONFIG_BASE64" ] || fail 'ACK_KUBE_CONFIG_BASE64 must be a File variable containing Base64 kubeconfig text.'

umask 077
ack_workdir=$(mktemp -d)
trap 'rm -rf "$ack_workdir"' EXIT
trap 'exit 1' HUP INT TERM
export KUBECONFIG="$ack_workdir/config"
base64 -d < "$ACK_KUBE_CONFIG_BASE64" > "$KUBECONFIG"
chmod 600 "$KUBECONFIG"
# --context is explicit on every operation; no modification of shared contexts.
pvc_phase=$(kubectl --context "$DEPLOY_ACK_NAME" --namespace "$DEPLOY_NAMESPACE" get pvc "$DATA_PVC_NAME" -o 'jsonpath={.status.phase}')
# WaitForFirstConsumer claims bind after pod scheduling, so Pending is allowed.
case "$pvc_phase" in Bound|Pending) ;; *) fail 'The assigned PVC is not available.' ;; esac
secret_keys=$(kubectl --context "$DEPLOY_ACK_NAME" --namespace "$DEPLOY_NAMESPACE" get secret "$APP_SECRET_NAME" -o 'go-template={{if and (index .data "ADMIN_PASSWORD") (index .data "GUEST_INVITE_CODE")}}ok{{end}}')
[ "$secret_keys" = ok ] || fail 'Application Secret needs ADMIN_PASSWORD and GUEST_INVITE_CODE.'
kubectl --context "$DEPLOY_ACK_NAME" --namespace "$DEPLOY_NAMESPACE" get secret "$IMAGE_PULL_SECRET_NAME" -o name
if [ "$TLS_MODE" = secret ]; then
  kubectl --context "$DEPLOY_ACK_NAME" --namespace "$DEPLOY_NAMESPACE" get secret "$TLS_SECRET_NAME" -o name
fi

helm upgrade --install "$DEPLOY_NAME" deploy/ack \
  --kube-context "$DEPLOY_ACK_NAME" --namespace "$DEPLOY_NAMESPACE" \
  -f deploy/ack/values-staging.yaml \
  --set-string "image.repository=$CI_REGISTRY_IMAGE" \
  --set-string "image.tag=vip-$CI_COMMIT_SHA" \
  --set-string "imagePullSecrets[0].name=$IMAGE_PULL_SECRET_NAME" \
  --set-string "persistence.existingClaim=$DATA_PVC_NAME" \
  --set-string "secrets.existingSecret=$APP_SECRET_NAME" \
  --set-string "ingress.className=$INGRESS_CLASS" \
  --set-string "ingress.host=$PUBLIC_HOST" \
  --set-string "ingress.tlsMode=$TLS_MODE" \
  --set-string "ingress.tlsSecretName=$TLS_SECRET_NAME" \
  --set-string "app.trustProxyHeaders=$TRUST_PROXY_HEADERS" \
  --atomic --wait --timeout "$HELM_TIMEOUT" --history-max 5
kubectl --context "$DEPLOY_ACK_NAME" --namespace "$DEPLOY_NAMESPACE" rollout status "deployment/$DEPLOY_NAME" --timeout="$HELM_TIMEOUT"
printf 'Deployment is ready. Test https://%s/ from a phone without VPN before sharing.\n' "$PUBLIC_HOST"

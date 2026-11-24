{{- define "vip.name" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "vip.selector" -}}
app.kubernetes.io/name: vip-reimbursement
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}
{{- define "vip.labels" -}}
{{ include "vip.selector" . }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

#!/bin/sh
# Healthy: no batch unit, or it is active and has finished building its table (ready file).
if ! systemctl cat patient-batch.service >/dev/null 2>&1; then echo "patient-batch not installed"; exit 0; fi
act=$(systemctl is-active patient-batch.service); res=$(systemctl show -p Result --value patient-batch.service)
mx=$(systemctl show -p MemoryMax --value patient-batch.service)
[ -e /run/patient-batch.ready ] && r=ready || r=not-ready
echo "patient-batch $act result=$res MemoryMax=$mx $r"
[ "$act" = active ] && [ "$r" = ready ]

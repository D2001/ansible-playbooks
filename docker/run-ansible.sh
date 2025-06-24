#!/usr/bin/env bash
# run-ansible.sh
# Timestamped logging wrapper for ansible-playbook
# -------------------------------------------------

export HOME="/home/karsten"
export PATH="/usr/local/bin:/usr/bin:/bin:/home/karsten/.local/bin"
export ANSIBLE_CONFIG="/home/karsten/ansible-playbooks/ansible.cfg"


# Set a full PATH that includes everything you need
# ---------- USER SETTINGS ----------
LOGDIR="/home/karsten/backups/logs"          # where logs are stored
TIMESTAMP_FORMAT="[%Y-%m-%d %H:%M:%S]"       # per-line timestamp
# ------------------------------------

# -- sanity check -----------------------------------------------------------
if [[ -z "$1" ]]; then
    echo "Usage: $0 <playbook.yml> [ansible-playbook options]" >&2
    exit 1
fi

PLAYBOOK="$1"; shift                         # $@ now holds extra ansible args
PLAYBOOK_BASE=$(basename "$PLAYBOOK" .yml)   # e.g. backup, restore

# --- pull service_name / service-name from the -e arguments ----------------
SERVICE_NAME="$PLAYBOOK_BASE"                # fallback if none given

NEXT_IS_E=0
for arg in "$@"; do
    # case 1: "-e" is on its own, next word holds the vars
    if [[ "$arg" == -e ]]; then
        NEXT_IS_E=1; continue
    fi

    # case 2: we’re reading that next word
    if [[ $NEXT_IS_E -eq 1 ]]; then
        for kv in $arg; do                  # handle multiple k=v pairs
            if [[ "$kv" =~ ^service[_-]name= ]]; then
                SERVICE_NAME="${kv#*=}"
                break
            fi
        done
        NEXT_IS_E=0; continue
    fi

    # case 3: "-eVAR=foo" written without a space
    if [[ "$arg" =~ ^-e ]]; then
        kv="${arg#-e}"
        kv="${kv#\"}"; kv="${kv%\"}"        # trim possible quotes
        for w in $kv; do
            if [[ "$w" =~ ^service[_-]name= ]]; then
                SERVICE_NAME="${w#*=}"
                break
            fi
        done
    fi
done
# ---------------------------------------------------------------------------

RUN_TS=$(date '+%Y-%m-%d_%H-%M-%S')
LOGFILE="${LOGDIR}/${SERVICE_NAME}_${PLAYBOOK_BASE}.log"

mkdir -p "$LOGDIR" || {
    echo "ERROR: Cannot create log directory $LOGDIR" >&2
    exit 1
}

# --- run ansible with line-by-line timestamps, tee to log ------------------
ansible-playbook -vv "$PLAYBOOK" "$@" \
  | ts "$TIMESTAMP_FORMAT" \
  | tee -a "$LOGFILE"
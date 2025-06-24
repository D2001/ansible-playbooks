#!/usr/bin/env bash
# run-ansible.sh
# Timestamped logging wrapper for ansible-playbook
# -------------------------------------------------

# Set environment for cron execution
export HOME="/home/karsten"
export PATH="/usr/local/bin:/usr/bin:/bin:/home/karsten/.local/bin"
export ANSIBLE_CONFIG="/home/karsten/ansible-playbooks/ansible.cfg"

# Ensure we're in the right directory
cd "/home/karsten/ansible-playbooks/docker" || {
    echo "ERROR: Cannot change to ansible-playbooks/docker directory" >&2
    exit 1
}
# ---------- USER SETTINGS ----------
LOGDIR="/home/karsten/backups/logs"          # where logs are stored
TIMESTAMP_FORMAT="[%Y-%m-%d %H:%M:%S]"       # per-line timestamp
# ------------------------------------

# Check for required commands
for cmd in ansible-playbook ts; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: Required command '$cmd' not found in PATH" >&2
        exit 1
    fi
done

# -- sanity check -----------------------------------------------------------
if [[ -z "$1" ]]; then
    # Default to backup.yml if no playbook specified (useful for cron)
    PLAYBOOK="/home/karsten/ansible-playbooks/docker/backup.yml"
    echo "No playbook specified, defaulting to: $PLAYBOOK" >&2
else
    PLAYBOOK="$1"; shift                     # $@ now holds extra ansible args
fi

# Check if playbook file exists
if [[ ! -f "$PLAYBOOK" ]]; then
    echo "ERROR: Playbook file '$PLAYBOOK' does not exist" >&2
    exit 1
fi
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
echo "Starting ansible-playbook: $PLAYBOOK" >&2
echo "Arguments: $@" >&2
echo "Log file: $LOGFILE" >&2

ansible-playbook -vv "$PLAYBOOK" "$@" \
  | ts "$TIMESTAMP_FORMAT" \
  | tee -a "$LOGFILE"

# Capture the exit status
EXIT_CODE=${PIPESTATUS[0]}
echo "[INFO] Ansible playbook completed with exit code: $EXIT_CODE" | ts "$TIMESTAMP_FORMAT" | tee -a "$LOGFILE"
exit $EXIT_CODE
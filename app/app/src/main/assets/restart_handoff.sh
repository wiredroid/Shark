#!/system/bin/sh
# Runs under the user's authorized Shizuku/Stellar shell. Never runs an exploit.
PATH=/system/bin:/system/xbin
export PATH
umask 077
BASE=$2
case "$BASE" in /data/local/tmp/shark-restart-handoff-[0-9]*) ;; *) exit 90;; esac
BOOT_FILE=/proc/sys/kernel/random/boot_id
LIMIT=420
STABLE=10
state="$BASE/attempt"
boot=$(cat "$BOOT_FILE") || exit 90
case "$boot" in ''|*[!a-zA-Z0-9-]*) exit 90;; esac
phase() { cat "$state/phase" 2>/dev/null; }
put_phase() { printf '%s\n' "$1" > "$state/phase.new" && mv "$state/phase.new" "$state/phase" && sync; }
pause() { printf '%s\n' "$*" > "$state/reason"; put_phase paused; echo "$*"; exit 91; }
zygote() { pidof zygote64 zygote; }
same_boot() { [ "$(cat "$BOOT_FILE")" = "$(cat "$state/boot")" ]; }
ready() {
    [ "$(getprop init.svc.zygote)" = running ] &&
    [ "$(getprop sys.boot_completed)" = 1 ] &&
    [ "$(timeout 3 am get-started-user-state 0 2>/dev/null)" = RUNNING_UNLOCKED ]
}
case "$1" in
    arm)
        case "$3:$4" in 0:0|0:1|0:2|0:3|1:0|1:1|1:2|1:3) ;; *) exit 92;; esac
        mkdir -p "$BASE" || exit 90
        mkdir "$BASE/control-$boot.lock" 2>/dev/null || exit 93
        trap 'rmdir "$BASE/control-$boot.lock"' EXIT
        if [ -d "$state" ]; then
            if ! same_boot; then
                mv "$state" "$BASE/history-$(date +%s)-$$" || exit 90
            else
                echo 'Another restart observer already exists. Manual root remains available.'
                exit 94
            fi
        fi
        mkdir "$state" || exit 90
        printf '%s\n' "$boot" > "$state/boot"
        zygote > "$state/before"
        [ -s "$state/before" ] || pause 'Cannot observe Zygote.'
        printf '%s\n' "$3" > "$state/second"
        printf '%s\n' "$4" > "$state/delay"
        printf '%s\n' "$5" > "$state/token"
        put_phase waiting || exit 90
        nohup setsid sh "$BASE/handoff.sh" watch "$BASE" </dev/null >>"$state/log" 2>&1 &
        echo "BOOT_ID=$boot"
        echo 'Restart handoff armed before root acquisition.' 
        ;;
    result)
        same_boot || exit 95
        printf '%s\n' "$3" > "$state/result"
        ;;
    cancel)
        [ ! -d "$state" ] || touch "$state/cancel"
        ;;
    status)
        if [ -d "$state" ]; then
            printf 'Handoff: %s (boot %s)\n' "$(phase)" "$(cat "$state/boot")"
            cat "$state/reason" 2>/dev/null
            cat "$state/log" 2>/dev/null
        else echo 'No handoff recorded.'; fi
        exit 0
        ;;
    reset)
        [ -d "$state" ] || exit 0
        if same_boot && [ "$(phase)" = waiting ]; then
            echo 'Cancel the waiting handoff before resetting.'
            exit 96
        fi
        mv "$state" "$BASE/history-$(date +%s)-$$" || exit 90
        ;;
    watch)
        mkdir "$state/worker.lock" 2>/dev/null || exit 93
        count=0
        good=0
        last=
        before=$(cat "$state/before")
        while [ "$count" -lt "$LIMIT" ]; do
            [ ! -f "$state/cancel" ] || pause 'Cancelled. No restart handoff.'
            same_boot || pause 'Physical boot changed. No automatic retry.'
            result=$(cat "$state/result" 2>/dev/null)
            case "$result" in ''|0) ;; *) pause "Root process failed ($result). No restart.";; esac
            current=$(zygote)
            observed=0
            [ -z "$current" ] || [ "$current" = "$before" ] || observed=1
            # The first framework restart can kill the Activity before waitFor returns.
            # Its changed PID is a durable completion signal; otherwise require exit 0.
            if { [ "$observed" = 1 ] || [ "$result" = 0 ]; } && ready; then
                if [ "$current" = "$last" ]; then good=$((good + 1)); else good=1; fi
                if [ "$good" -ge "$STABLE" ]; then
                    [ ! -f "$state/cancel" ] || pause 'Cancelled before handoff.'
                    same_boot || pause 'Physical boot changed before handoff.'
                    second=$(cat "$state/second")
                    delay=$(cat "$state/delay")
                    # Mark before executing; ambiguous command results must never replay.
                    put_phase handed_off || exit 90
                    token=$(cat "$state/token")
                    case "$token" in ''|*[!a-zA-Z0-9-]*) pause 'Invalid handoff token.';; esac
                    echo "First restart observed=$observed; dispatching to Shark's own root grant."
                    if [ "$observed" = 1 ]; then first=true; else first=false; fi
                    # Android may defer even urgent broadcasts to a cached app.
                    # Wake the existing Activity first; it never starts root on resume.
                    timeout 12 am start --activity-single-top -n com.shark.kty/.MainActivity >"$state/wakeup.log" 2>&1 ||
                        pause 'Could not bring Shark forward for continuation. Manual root remains available.'
                    timeout 12 am broadcast --receiver-foreground --include-stopped-packages \
                        -n com.shark.kty/.RestartHandoffReceiver \
                        -a com.shark.kty.CONTINUE_RESTART \
                        --es token "$token" --es boot "$boot" --ez first_observed "$first"
                    rc=$?
                    [ "$rc" = 0 ] || pause "App handoff failed ($rc). Manual root remains available."
                    exit 0
                fi
            else good=0; fi
            last="$current"
            sleep 1
            count=$((count + 1))
        done
        pause 'Timed out waiting for a completed root run and stable Android. Manual root remains available.'
        ;;
    *) exit 97;;
esac

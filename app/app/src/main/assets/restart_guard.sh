#!/system/bin/sh
# Root must already exist. This controller never obtains root or changes modules.
PATH=/system/bin:/system/xbin
export PATH
umask 077
BASE=/data/adb/shark-restart-guard
BOOT_FILE=/proc/sys/kernel/random/boot_id
SELF=/data/adb/shark-restart-guard/controller.sh
LIMIT=180
STABLE=15
mkdir -p "$BASE" || exit 70
[ "$(id -u)" = 0 ] || exit 71
boot=$(cat "$BOOT_FILE") || exit 72
case "$boot" in ''|*[!a-zA-Z0-9-]*) exit 72;; esac
state="$BASE/attempt"
phase() { cat "$state/phase" 2>/dev/null; }
put_phase() {
    printf '%s\n' "$1" > "$state/phase.new" &&
        mv "$state/phase.new" "$state/phase" && sync
}
pause() {
    printf '%s\n' "$*" > "$state/reason"
    put_phase paused
    echo "Restart paused: $*"
    exit 73
}
same_boot() { [ "$(cat "$BOOT_FILE")" = "$(cat "$state/boot")" ]; }
zygote() { pidof zygote64 zygote; }
ready() {
    [ "$(getprop init.svc.zygote)" = running ] &&
    [ "$(getprop sys.boot_completed)" = 1 ] &&
    [ "$(timeout 3 am get-started-user-state 0 2>/dev/null)" = RUNNING_UNLOCKED ]
}
wait_ready() {
    old="$1"
    count=0
    good=0
    last=
    while [ "$count" -lt "$LIMIT" ]; do
        [ ! -f "$state/cancel" ] || pause 'Cancelled by user. No further restart.'
        same_boot || pause 'Physical boot changed; automatic continuation refused.'
        current=$(zygote)
        if [ -n "$current" ] && [ "$current" != "$old" ] && ready; then
            if [ "$current" = "$last" ]; then good=$((good + 1)); else good=1; fi
            [ "$good" -ge "$STABLE" ] && return 0
        else
            good=0
        fi
        last="$current"
        sleep 1
        count=$((count + 1))
    done
    pause 'Android did not become stable and unlocked in time. No restart retry.'
}
restart_once() {
    [ ! -f "$state/cancel" ] || pause 'Cancelled by user. No further restart.'
    same_boot || pause 'Physical boot changed.'
    old=$(zygote)
    [ -n "$old" ] || pause 'Zygote not running.'
    ready || pause 'Android is not ready or owner is locked.'
    put_phase "$1" || exit 74
    setprop ctl.restart zygote || pause 'Framework restart request failed.'
    wait_ready "$old"
}
case "$1" in
    cancel)
        if [ -d "$state" ]; then
            touch "$state/cancel" || exit 74
            echo 'Cancellation recorded. A restart already requested cannot be undone.'
        fi
        ;;
    status)
        if [ -d "$state" ]; then
            printf 'Restart sequence: %s\n' "$(phase)"
            cat "$state/reason" 2>/dev/null
        else echo 'No restart sequence recorded.'; fi
        exit 0
        ;;
    reset)
        mkdir "$BASE/control.lock" 2>/dev/null || exit 75
        trap 'rmdir "$BASE/control.lock"' EXIT
        case "$(phase)" in
            paused|complete) ;;
            '') exit 0;;
            *)
                same_boot && { echo 'An active or interrupted attempt cannot be reset in this boot.'; exit 76; }
                ;;
        esac
        mv "$state" "$BASE/history-$(date +%s)-$$" || exit 77
        echo 'Safety hold acknowledged. No module was enabled or disabled.'
        ;;
    launch)
        case "$2:$3" in 0:0|0:1|0:2|0:3|1:0|1:1|1:2|1:3) ;; *) exit 78;; esac
        mkdir "$BASE/control.lock" 2>/dev/null || { echo 'Another request is in progress.'; exit 75; }
        trap 'rmdir "$BASE/control.lock"' EXIT
        if [ -d "$state" ]; then
            if ! same_boot && [ "$(phase)" = complete ]; then
                mv "$state" "$BASE/history-$(date +%s)-$$" || exit 77
            else
                echo "Existing restart attempt: $(phase). No additional restart scheduled."
                exit 79
            fi
        fi
        ready || { echo 'Unlock the owner and wait for Android to finish starting.'; exit 80; }
        command -v setsid >/dev/null && command -v nohup >/dev/null && command -v timeout >/dev/null || exit 81
        # Retire ONLY the byte-for-byte legacy hook shipped by this app. Preserve
        # it outside the executable hook directory; unknown recovery tools stay intact.
        legacy=/data/adb/post-fs-data.d/shark_rescue.sh
        if [ -f "$legacy" ]; then
            checksum=$(sha256sum "$legacy")
            if [ "${checksum%% *}" != 33648a55180d05c0066b721d2ee14df40dc4364639bf3f39cab57612b3f86c1a ]; then
                echo 'Unknown legacy rescue hook. No restart scheduled; manual review required.'
                exit 82
            fi
            mv "$legacy" "$BASE/legacy-rescue-$(date +%s)-$$.txt" || exit 82
        fi
        mkdir "$state" || exit 83
        printf '%s\n' "$boot" > "$state/boot" || exit 74
        if [ -f /data/adb/shark_boot_flag ]; then
            mv /data/adb/shark_boot_flag "$state/legacy-boot-flag" || exit 82
            pause 'Legacy restart was unfinished. Review modules, then acknowledge the safety hold.'
        fi
        printf '%s\n' "$2" > "$state/second" || exit 74
        printf '%s\n' "$3" > "$state/delay" || exit 74
        put_phase queued || exit 74
        nohup setsid sh "$SELF" run </dev/null >>"$state/log" 2>&1 &
        echo 'Restart sequence queued. Unlock after each restart; disabled modules are preserved.'
        ;;
    run)
        [ -d "$state" ] || exit 84
        mkdir "$state/worker.lock" 2>/dev/null || exit 85
        same_boot || pause 'Attempt belongs to a different physical boot.'
        [ "$(phase)" = queued ] || pause 'Refusing to replay an interrupted stage.'
        sleep 2
        restart_once first_requested
        put_phase first_verified || exit 74
        if [ "$(cat "$state/second")" = 1 ]; then
            delay=$(cat "$state/delay")
            case "$delay" in 0) seconds=12;; 1|2|3) seconds=$((delay * 60));; *) pause 'Invalid delay.';; esac
            sleep "$seconds"
            restart_once second_requested
        fi
        put_phase complete || exit 74
        echo 'Requested framework restarts completed. Module functionality still requires verification.'
        ;;
    *) exit 86;;
esac

#!/system/bin/sh
# Root must already exist. This controller never obtains root or changes modules.
PATH=/system/bin:/system/xbin
export PATH
umask 077
BASE=/data/adb/shark-restart-guard
BOOT_FILE=/proc/sys/kernel/random/boot_id
SELF=/data/adb/shark-restart-guard/controller.sh
RECEIPT=/data/user/0/com.shark.kty/files/automatic-boot-complete
LIMIT=180
STABLE=15
mkdir -p "$BASE" || exit 70
[ "$(id -u)" = 0 ] || exit 71
boot=$(cat "$BOOT_FILE") || exit 72
case "$boot" in ''|*[!a-zA-Z0-9-]*) exit 72;; esac
state="$BASE/attempt"
control="$BASE/control-$boot.lock"
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
    # Use the Manager's operation so enabled modules receive their boot stages.
    # Restarting Zygote alone does not initialize the module runtime.
    [ -x /data/adb/ksud ] || pause 'KernelSU daemon unavailable. No restart requested.'
    /data/adb/ksud soft-reboot || pause 'KernelSU soft reboot request failed.'
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
            printf 'Restart sequence: %s (boot %s)\n' "$(phase)" "$(cat "$state/boot")"
            same_boot || echo 'This result belongs to an earlier physical boot.'
            cat "$state/reason" 2>/dev/null
        else echo 'No restart sequence recorded.'; fi
        exit 0
        ;;
    reset)
        mkdir "$control" 2>/dev/null || exit 75
        trap 'rmdir "$control"' EXIT
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
        observed=${4:-0}
        case "$observed" in 0|1) ;; *) exit 78;; esac
        mkdir "$control" 2>/dev/null || { echo 'Another request is in progress.'; exit 75; }
        trap 'rmdir "$control"' EXIT
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
        printf '%s\n' "$observed" > "$state/first_observed" || exit 74
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
        observed=$(cat "$state/first_observed" 2>/dev/null)
        case "$observed" in
            1)
                # The authorized handoff witnessed the first restart while the
                # Activity was dying. Do not turn two requested restarts into three.
                ready || pause 'Observed first restart is no longer healthy.'
                echo 'First framework restart was observed before handoff.'
                ;;
            ''|0) restart_once first_requested;;
            *) pause 'Invalid first-restart observation.';;
        esac
        put_phase first_verified || exit 74
        if [ "$(cat "$state/second")" = 1 ]; then
            delay=$(cat "$state/delay")
            case "$delay" in 0) seconds=12;; 1|2|3) seconds=$((delay * 60));; *) pause 'Invalid delay.';; esac
            sleep "$seconds"
            restart_once second_requested
        fi
        put_phase complete || exit 74
        # MainActivity creates this file with its own UID and SELinux category.
        # Preserve both by writing the existing file only; an interrupted write fails closed.
        if [ -f "$RECEIPT" ] && [ ! -L "$RECEIPT" ]; then
            printf '%s\n' "$boot" > "$RECEIPT" || echo 'Could not save the automatic-boot completion receipt.'
        fi
        echo 'Requested framework restarts completed. Module functionality still requires verification.'
        ;;
    *) exit 86;;
esac

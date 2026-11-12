package com.shark.kty

import android.util.Base64

/**
 * Arms a one-shot recovery hook before a userspace reboot. If Android reaches
 * boot_completed, the hook clears its marker; otherwise the next boot removes
 * only modules associated with Shark-managed features.
 */
object ModuleCircuitBreaker {
    private const val MARKER = "/data/adb/.shark_circuit_breaker"
    private const val HOOK = "/data/adb/service.d/shark-circuit-breaker.sh"

    private val hook = """
        #!/system/bin/sh
        MARKER=$MARKER
        [ -f "${'$'}MARKER" ] || exit 0
        state="${'$'}(sed -n '1p' "${'$'}MARKER")"
        if [ "${'$'}state" = armed ]; then
            sed -i '1s/^armed${'$'}/booting/' "${'$'}MARKER"
            sleep 90
            if [ "${'$'}(getprop sys.boot_completed)" = 1 ]; then
                rm -f "${'$'}MARKER"
                exit 0
            fi
        fi
        if [ "${'$'}state" = booting ] || [ "${'$'}(sed -n '1p' "${'$'}MARKER")" = booting ]; then
            tail -n +2 "${'$'}MARKER" | while IFS= read -r module; do
                case "${'$'}module" in
                    /data/adb/modules/*)
                        [ -d "${'$'}module" ] && rm -rf -- "${'$'}module"
                        ;;
                esac
            done
            rm -f "${'$'}MARKER"
        fi
    """.trimIndent()

    fun arm(command: (String) -> Pair<Int, String>): Pair<Int, String> {
        val encodedHook = Base64.encodeToString(hook.toByteArray(), Base64.NO_WRAP)
        val script = """
            mkdir -p /data/adb/service.d
            echo $encodedHook | base64 -d > '$HOOK'
            chmod 0755 '$HOOK'
            {
                echo armed
                find /data/adb/modules -mindepth 1 -maxdepth 1 -type d 2>/dev/null |
                    while IFS= read -r module; do
                        case "${'$'}module" in
                            *shark*|*susfs*|*droidspaces*|*hybridmount*)
                                echo "${'$'}module"
                                ;;
                        esac
                    done
            } > '$MARKER'
            chmod 0600 '$MARKER'
        """.trimIndent()
        return command(script)
    }
}

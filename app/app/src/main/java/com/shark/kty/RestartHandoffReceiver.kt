package com.shark.kty

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import java.io.File
import java.util.concurrent.TimeUnit

/** Receives only an explicit, DUMP-permission protected handoff; never obtains root. */
class RestartHandoffReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != ACTION) return
        val result = goAsync()
        Thread {
            try { continueRestart(context.applicationContext, intent) }
            finally { result.finish() }
        }.start()
    }

    companion object {
        const val ACTION = "com.shark.kty.CONTINUE_RESTART"
        private fun quote(s: String) = "'" + s.replace("'", "'\"'\"'") + "'"

        @Synchronized
        private fun continueRestart(context: Context, intent: Intent) {
            val prefs = context.getSharedPreferences("restart_handoff", Context.MODE_PRIVATE)
            val token = intent.getStringExtra("token") ?: return
            val boot = intent.getStringExtra("boot") ?: return
            if (token != prefs.getString("token", null) || boot != prefs.getString("boot", null)) return
            if (prefs.getBoolean("claimed", false)) return
            val second = if (prefs.getBoolean("second", false)) 1 else 0
            val delay = prefs.getInt("delay", 0).coerceIn(0, 3)
            val observed = if (intent.getBooleanExtra("first_observed", false)) 1 else 0
            val settings = context.getSharedPreferences("pyb110", Context.MODE_PRIVATE)
            if (!settings.getBoolean("soft_reboot_after", false)) return
            val actualSecond = if (settings.getBoolean("second_soft_reboot", false)) second else 0
            if (!prefs.edit().putBoolean("claimed", true).commit()) return
            val status = File(context.filesDir, "restart-handoff-result.txt")
            try {
                val controller = context.assets.open("restart_guard.sh").bufferedReader().use { it.readText() }
                val script = """
                    [ "${'$'}(id -u)" = 0 ] || exit 71
                    [ "${'$'}(cat /proc/sys/kernel/random/boot_id)" = ${quote(boot)} ] || exit 72
                    umask 077
                    mkdir -p /data/adb/shark-restart-guard || exit 70
                    printf '%s' ${quote(controller)} > /data/adb/shark-restart-guard/controller.sh.new || exit 70
                    chmod 700 /data/adb/shark-restart-guard/controller.sh.new || exit 70
                    mv /data/adb/shark-restart-guard/controller.sh.new /data/adb/shark-restart-guard/controller.sh || exit 70
                    exec sh /data/adb/shark-restart-guard/controller.sh launch $actualSecond $delay $observed
                """.trimIndent()
                // Use Shark's existing grant, not the shell UID's possibly restricted grant.
                // Never retry a mutating command through a different transport.
                val p = ProcessBuilder("/system/bin/su", "-c", script).redirectErrorStream(true).start()
                val output = StringBuilder()
                val reader = Thread {
                    runCatching { p.inputStream.bufferedReader().forEachLine { synchronized(output) { if (output.length < 16384) output.appendLine(it) } } }
                }.apply { isDaemon = true; start() }
                val rc = if (p.waitFor(6, TimeUnit.SECONDS)) p.exitValue() else {
                    p.destroyForcibly()
                    -2
                }
                reader.join(500)
                status.writeText("App handoff on boot $boot: result $rc\n" + synchronized(output) { output.toString() })
            } catch (e: Exception) {
                status.writeText("Automatic restarts unavailable on boot $boot: ${e.message}. Manual root remains available.\n")
            }
        }
    }
}

package com.shark.kty

import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.UserManager
import java.io.File
import java.util.UUID
import kotlinx.coroutines.*

/** Reuses the earlier recovery design: owner unlock, authorized helper, one physical-boot attempt. */
internal object BootAutomation {
    const val ACTION = "com.shark.kty.AUTOMATIC_BOOT_RECOVERY"
    private const val JOB = 0x534852
    private const val PREFS = "automatic_boot"
    private fun prefs(c: Context) = c.createDeviceProtectedStorageContext()
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    fun enabled(c: Context) = prefs(c).getBoolean("enabled", false)
    fun unlocked(c: Context): Boolean = c.getSystemService(UserManager::class.java)
        ?.let { it.isSystemUser && it.isUserUnlocked } == true
    fun receipt(c: Context) = File(c.filesDir, "automatic-boot-complete")
    fun message(c: Context): String {
        val attempted = prefs(c).getString("attempted", null)
        if (unlocked(c) && !attempted.isNullOrBlank() &&
            runCatching { receipt(c).readText().trim() }.getOrNull() == attempted)
            return "Automatic sequence completed"
        return prefs(c).getString("message", "Off") ?: "Off"
    }
    fun status(c: Context, text: String) { prefs(c).edit().putString("message", text).apply() }
    private fun quote(s: String) = "'" + s.replace("'", "'\"'\"'") + "'"

    fun shell(command: String): Pair<Int, String> {
        val p = PrivService.newProcess(arrayOf("/system/bin/timeout", "12", "sh", "-c", command),
            arrayOf("PATH=/system/bin:/system/xbin:/data/adb/ksu/bin", "HOME=/"), "/")
        val error = StringBuilder()
        val reader = Thread { runCatching { p.getErrorStream().bufferedReader().forEachLine {
            if (error.length < 2048) error.appendLine(it)
        } } }.apply { isDaemon = true; start() }
        val out = p.getInputStream().bufferedReader().use { it.readText() }
        val rc = p.waitFor()
        reader.join(500)
        return rc to out.trim()
    }

    fun physicalBoot(): String? {
        if (!PrivService.granted()) return null
        val (rc, out) = shell("cat /proc/sys/kernel/random/boot_id")
        return out.takeIf { rc == 0 && it.matches(Regex("[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")) }
    }

    /** Enabling arms the NEXT full boot and explicitly acknowledges an earlier hold. */
    @Synchronized fun setEnabled(c: Context, value: Boolean): Boolean {
        if (!value) {
            prefs(c).edit().putBoolean("enabled", false).remove("pending_token").commit()
            c.getSystemService(JobScheduler::class.java)?.cancel(JOB)
            status(c, "Off")
            return true
        }
        if (!unlocked(c)) return false
        val boot = physicalBoot() ?: return false
        receipt(c).apply { if (!exists()) createNewFile() }
        val saved = prefs(c).edit().putBoolean("enabled", true).putString("baseline", boot)
            .remove("attempted").remove("pending_token").remove("pending_boot")
            .putString("message", "Armed for the next full restart").commit()
        if (saved) schedule(c)
        return saved
    }

    fun schedule(c: Context) {
        val scheduler = c.getSystemService(JobScheduler::class.java) ?: return
        if (!enabled(c)) { scheduler.cancel(JOB); return }
        if (scheduler.getPendingJob(JOB) != null) return
        val job = JobInfo.Builder(JOB, ComponentName(c, BootAutomationService::class.java))
            .setPersisted(true).setMinimumLatency(5_000)
            .setBackoffCriteria(30_000, JobInfo.BACKOFF_POLICY_EXPONENTIAL)
            .build()
        if (scheduler.schedule(job) != JobScheduler.RESULT_SUCCESS)
            status(c, "Android did not schedule startup; check Auto launch")
    }

    @Synchronized private fun decision(c: Context, boot: String): BootAutomationPolicy.Decision {
        val p = prefs(c)
        val complete = runCatching { receipt(c).readText().trim() }.getOrNull()
        return BootAutomationPolicy.decide(enabled(c), unlocked(c), boot,
            p.getString("baseline", null), p.getString("attempted", null), complete)
    }

    /** No native work is submitted by a background job. The foreground Activity owns it. */
    @Synchronized fun dispatch(c: Context, boot: String): Boolean {
        when (decision(c, boot)) {
            BootAutomationPolicy.Decision.WAIT -> return false
            BootAutomationPolicy.Decision.ALREADY_HANDLED -> return true
            BootAutomationPolicy.Decision.PAUSED -> {
                status(c, "Paused after an unfinished attempt; review it before re-enabling startup")
                return true
            }
            BootAutomationPolicy.Decision.RUN -> Unit
        }
        val token = UUID.randomUUID().toString()
        if (!prefs(c).edit().putString("pending_token", token).putString("pending_boot", boot).commit()) return false
        val (rc, _) = shell("am start --activity-single-top -n com.shark.kty/.MainActivity -a $ACTION --es boot_token ${quote(token)}")
        if (rc != 0) { status(c, "Waiting for Android to open Shark"); return false }
        status(c, "Opening Shark for this boot's recovery")
        return true
    }

    /** A public Activity intent alone cannot obtain root; the saved one-use token must match. */
    @Synchronized fun claim(c: Context, intent: Intent, actualBoot: String): Boolean {
        val p = prefs(c)
        val token = intent.getStringExtra("boot_token") ?: return false
        if (intent.action != ACTION || token != p.getString("pending_token", null) ||
            actualBoot != p.getString("pending_boot", null) || decision(c, actualBoot) != BootAutomationPolicy.Decision.RUN) return false
        return p.edit().putString("attempted", actualBoot).remove("pending_token")
            .putString("message", "Recovering root and enabled modules").commit()
    }
}

class BootAutomationReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_LOCKED_BOOT_COMPLETED,
                Intent.ACTION_USER_UNLOCKED, Intent.ACTION_MY_PACKAGE_REPLACED)) BootAutomation.schedule(context)
    }
}

class BootAutomationService : JobService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var work: Job? = null
    override fun onStartJob(params: JobParameters): Boolean {
        if (!BootAutomation.enabled(this)) return false
        work = scope.launch {
            var retry = true
            try {
                if (!BootAutomation.unlocked(this@BootAutomationService)) {
                    BootAutomation.status(this@BootAutomationService, "Waiting for owner unlock")
                } else {
                    for (attempt in 0 until 20) {
                        ensureActive()
                        if (PrivService.granted()) break
                        BootAutomation.status(this@BootAutomationService, "Waiting for authorized Shevery, Shizuku or Stellar")
                        delay(1500)
                    }
                    val boot = BootAutomation.physicalBoot()
                    if (boot != null) retry = !BootAutomation.dispatch(this@BootAutomationService, boot)
                }
            } catch (cancelled: CancellationException) { throw cancelled
            } catch (_: Exception) {
                BootAutomation.status(this@BootAutomationService, "Waiting for the authorized helper to reconnect")
            } finally {
                if (currentCoroutineContext().isActive) withContext(Dispatchers.Main) {
                    jobFinished(params, retry && BootAutomation.enabled(this@BootAutomationService))
                }
            }
        }
        return true
    }
    override fun onStopJob(params: JobParameters): Boolean { work?.cancel(); return BootAutomation.enabled(this) }
    override fun onDestroy() { scope.cancel(); super.onDestroy() }
}

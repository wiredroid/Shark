package com.shark.kty

/** A physical boot identity, not a framework restart or module count, bounds recovery. */
internal object BootAutomationPolicy {
    enum class Decision { WAIT, ALREADY_HANDLED, PAUSED, RUN }

    fun decide(enabled: Boolean, unlocked: Boolean, boot: String?, baseline: String?,
               attempted: String?, completed: String?): Decision {
        if (!enabled || !unlocked || boot.isNullOrBlank()) return Decision.WAIT
        if (boot == baseline || boot == attempted) return Decision.ALREADY_HANDLED
        if (!attempted.isNullOrBlank() && completed != attempted) return Decision.PAUSED
        return Decision.RUN
    }
}

/** Automatic startup only; manual root never waits for this gate. */
internal class BootStartupReadiness {
    private var readySince: Long? = null
    private var lastSample: Long? = null

    fun observe(uptimeMs: Long, unlocked: Boolean, helperReady: Boolean, bootCompleted: Boolean): Boolean {
        val previous = lastSample
        lastSample = uptimeMs
        // A suspended job or a lost helper must earn a fresh continuous window.
        if (previous != null && (uptimeMs < previous || uptimeMs - previous > 10_000)) readySince = null
        if (!unlocked || !helperReady || !bootCompleted || uptimeMs < 0) {
            readySince = null
            return false
        }
        val since = readySince ?: uptimeMs.also { readySince = it }
        return uptimeMs >= 120_000 && uptimeMs - since >= 30_000
    }
}

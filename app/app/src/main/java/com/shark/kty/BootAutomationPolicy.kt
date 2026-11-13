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

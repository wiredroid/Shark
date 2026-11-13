package com.shark.kty

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BootAutomationPolicyTest {
    private val run = BootAutomationPolicy.Decision.RUN
    private val wait = BootAutomationPolicy.Decision.WAIT
    private val done = BootAutomationPolicy.Decision.ALREADY_HANDLED
    private val pause = BootAutomationPolicy.Decision.PAUSED
    @Test fun disabledNeverStarts() { assertEquals(wait, BootAutomationPolicy.decide(false,true,"b",null,null,null)) }
    @Test fun lockedOwnerNeverStarts() { assertEquals(wait, BootAutomationPolicy.decide(true,false,"b",null,null,null)) }
    @Test fun unavailablePhysicalBootNeverStarts() { assertEquals(wait, BootAutomationPolicy.decide(true,true,null,null,null,null)) }
    @Test fun enablingDoesNotRootTheCurrentBoot() { assertEquals(done, BootAutomationPolicy.decide(true,true,"a","a",null,null)) }
    @Test fun nextFullBootStartsOnce() { assertEquals(run, BootAutomationPolicy.decide(true,true,"b","a",null,null)) }
    @Test fun frameworkRestartDoesNotReplayRoot() { assertEquals(done, BootAutomationPolicy.decide(true,true,"b","a","b",null)) }
    @Test fun completedAttemptDoesNotReplayInSameBoot() { assertEquals(done, BootAutomationPolicy.decide(true,true,"b","a","b","b")) }
    @Test fun incompletePreviousBootPausesAutomaticRecovery() { assertEquals(pause, BootAutomationPolicy.decide(true,true,"c","a","b",null)) }
    @Test fun staleReceiptCannotAuthorizeAnotherAttempt() { assertEquals(pause, BootAutomationPolicy.decide(true,true,"c","a","b","a")) }
    @Test fun completedPreviousBootAllowsNewFullBoot() { assertEquals(run, BootAutomationPolicy.decide(true,true,"c","a","b","b")) }
    private fun feed(gate: BootStartupReadiness, start: Long, end: Long): Boolean {
        var ready = false
        for (t in start..end step 2_000) ready = gate.observe(t, true, true, true)
        return ready
    }
    @Test fun earlyBootCannotStartEvenWithAuthorizedHelper() {
        val gate = BootStartupReadiness()
        assertFalse(feed(gate, 0, 118_000))
        assertTrue(gate.observe(120_000, true, true, true))
    }
    @Test fun lateHelperStillNeedsThirtySeconds() {
        val gate = BootStartupReadiness()
        assertFalse(feed(gate, 300_000, 328_000))
        assertTrue(gate.observe(330_000, true, true, true))
    }
    @Test fun relockResetsSettlingWindow() {
        val gate = BootStartupReadiness()
        feed(gate, 300_000, 328_000)
        assertFalse(gate.observe(330_000, false, true, true))
        assertFalse(feed(gate, 332_000, 360_000))
        assertTrue(gate.observe(362_000, true, true, true))
    }
    @Test fun helperLossResetsSettlingWindow() {
        val gate = BootStartupReadiness()
        feed(gate, 300_000, 328_000)
        assertFalse(gate.observe(330_000, true, false, true))
        assertFalse(feed(gate, 332_000, 360_000))
        assertTrue(gate.observe(362_000, true, true, true))
    }
    @Test fun frameworkRestartResetsSettlingWindow() {
        val gate = BootStartupReadiness()
        feed(gate, 300_000, 328_000)
        assertFalse(gate.observe(330_000, true, true, false))
        assertFalse(feed(gate, 332_000, 360_000))
        assertTrue(gate.observe(362_000, true, true, true))
    }
    @Test fun suspendedJobDoesNotCountAsObservedStability() {
        val gate = BootStartupReadiness()
        feed(gate, 300_000, 320_000)
        assertFalse(gate.observe(360_000, true, true, true))
        assertFalse(feed(gate, 362_000, 388_000))
        assertTrue(gate.observe(390_000, true, true, true))
    }
    @Test fun backwardClockResetsSettlingWindow() {
        val gate = BootStartupReadiness()
        feed(gate, 300_000, 328_000)
        assertFalse(gate.observe(120_000, true, true, true))
        assertFalse(feed(gate, 122_000, 148_000))
        assertTrue(gate.observe(150_000, true, true, true))
    }
}

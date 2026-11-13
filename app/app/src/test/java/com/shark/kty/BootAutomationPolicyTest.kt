package com.shark.kty

import org.junit.Assert.assertEquals
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
}

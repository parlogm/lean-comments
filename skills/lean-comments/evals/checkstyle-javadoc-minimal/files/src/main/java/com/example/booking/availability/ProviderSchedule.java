package com.example.booking.availability;

import java.time.DayOfWeek;
import java.util.Set;
import java.util.UUID;

public class ProviderSchedule {
    /** Provider this schedule belongs to. */
    private final UUID providerId;

    /** Days the provider works; empty means on leave. */
    private final Set<DayOfWeek> workingDays;

    public ProviderSchedule(UUID providerId, Set<DayOfWeek> workingDays) {
        this.providerId = providerId;
        this.workingDays = workingDays;
    }

    public UUID getProviderId() {
        return providerId;
    }

    public boolean worksOn(DayOfWeek day) {
        return workingDays.contains(day);
    }
}

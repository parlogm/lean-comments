package com.example.reports.entitlement;

import java.util.UUID;

public interface EntitlementGateway {
    boolean isEntitled(UUID accountId, String feature);
}

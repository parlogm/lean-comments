package com.example.onboarding.partner;

public interface PartnerClient {
    String registerCustomer(String customerId, String referralCode);

    void deleteCustomer(String customerId);
}

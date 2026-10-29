package com.example.onboarding.partner;

import java.util.logging.Logger;

/**
 * Signs our customers up with the partner platform.
 *
 * <p>The referral code can only be sent while creating the customer. The partner's order API has
 * nowhere to put it, and there is no call to add one to a customer who already exists, so a wrong or
 * missing code here is permanent and finance has to reconcile the commission by hand.
 *
 * <p>There is intentionally no retry. When a registration call times out, the partner has often
 * created the customer anyway, and sending the request again produces a second customer record that
 * someone then has to find and merge manually.
 */
public class RegistrationService {

    private static final Logger LOG = Logger.getLogger(RegistrationService.class.getName());

    private final PartnerClient partnerClient;

    public RegistrationService(PartnerClient partnerClient) {
        this.partnerClient = partnerClient;
    }

    /**
     * Registers the customer together with their referral code.
     *
     * <p>This must be the code the partner issued, not our own marketing campaign id. They have the
     * same format and were mixed up during the pilot, so the parameter name spells it out.
     */
    public String register(String customerId, String partnerReferralCode) {
        // Only the customer id may be logged here. The request and any error body from the partner
        // include names and email addresses, and our application logs are forwarded to a third-party
        // service that we are not allowed to send personal data to.
        LOG.info(() -> "Registering partner customer " + customerId);
        return partnerClient.registerCustomer(customerId, partnerReferralCode);
    }
}

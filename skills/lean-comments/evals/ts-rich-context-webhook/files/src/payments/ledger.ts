export interface Ledger {
  hasRefund(refundId: string): Promise<boolean>;
  recordRefund(orderId: string, refundId: string, amountDollars: number): Promise<void>;
}

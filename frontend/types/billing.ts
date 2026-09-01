export type BillingStatus = {
  organization: {
    id: number
    name: string
  }
  subscription: BillingSubscription | null
  effective_modules: BillingModule[]
  recent_notifications: BillingNotification[]
}

export type BillingSubscription = {
  public_id: string
  status: string
  plan: {
    code: string
    name: string
  }
  started_at: string | null
  trial_ends_at: string | null
  past_due_since: string | null
  grace_until: string | null
  current_period_start: string | null
  current_period_end: string | null
  cancelled_at: string | null
}

export type BillingModule = {
  code: string
  name: string
  limits: Record<string, unknown>
}

export type BillingNotification = {
  type: string
  period_start: string | null
  period_end: string | null
  delivered_at: string | null
  created_at: string
}

export type BillingInvoice = {
  public_id: string
  number: string
  amount: string
  status: string
  due_date: string
  period_start: string | null
  period_end: string | null
  paid_at: string | null
  plan: {
    code: string
    name: string
  }
}

export type BillingInvoicePage = {
  count: number
  next: string | null
  previous: string | null
  results: BillingInvoice[]
}

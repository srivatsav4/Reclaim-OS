# RECLAIM OS: 3-minute demo script

All data is DEMO / SIMULATED. Click **Reset demo** on the Command Center first (scenario cases start unexecuted).

1. **Command Center** (0:00) "RECLAIM OS has identified ~₹38.6L of revenue at risk (demo data). Only part of it is worth chasing: see the funnel: at risk → eligible → targeted → recovered."
2. **Risk Graph** (0:25) Open *Revenue Risk Graph* → Aarav Sharma. "One customer, four leaks: checkout, payment, subscription, invoice: ₹1,18,500 exposure, not four unrelated tickets."
3. **Scenario 2, ₹85,000** (0:50) Command Center → *₹85,000 high-value failure → payment link*. "Expired card, so retry is blocked by policy. Four-plus candidate actions, each with probability, cost, friction and expected value. The optimizer picks the best *permitted* one: payment link."
4. **Execute** (1:20) Click **EXECUTE** → SUCCESS, ₹85,000 recovered (simulated). Open the audit timeline on the same page: risk calculated → policy checked → action allowed → executed → payment succeeded.
5. **Scenario 3, ₹4,80,000** (1:40) "Above the ₹1,00,000 threshold: the agent cannot act alone." Human Review → **Approve** → executed, audited.
6. **Scenario 1 / 6** (2:00, optional) Retry success and checkout recovery.
7. **AI vs Control** (2:15) Back on the Command Center. "Observed recovery and *estimated incremental* recovery are separate numbers, labelled simulated." Run the experiment with another seed.
8. **Scenarios 4 and 5: knowing when not to act** (2:40) *Customer already paid* → NO ACTION. *Retry limit exceeded* → every action BLOCKED, with the blocked top action shown.
9. **Close** (3:00) "RECLAIM OS doesn't just find revenue leakage. It decides where recovery effort is worth spending, acts within strict boundaries, and measures the outcome."

Optional: **Recovery Lab**: compare *AI optimizer* vs *Blanket outreach* (policy violations) with *Compare all*.

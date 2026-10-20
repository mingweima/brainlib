# Event-Study Specification Checklist

Pre-submission checks before exporting event-study figures from the enclave.

## Steps
1. Verify that event time `k = -1` (the quarter immediately before remote adoption) is omitted as the reference period.
2. Check that cohort treatment timing never resets for firms that later adjust hybrid attendance days.
3. Plot both conventional two-way fixed effects and cohort-weighted estimates on the same axes with 95% confidence bands.
4. Report the joint F-test p-value for pre-treatment leads `k = -8` through `k = -2` in the figure note.

Remember to add any failed robustness specs to [[todo]] before freezing the replication package.

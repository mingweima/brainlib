# Two-Way Clustered Standard Errors in Python

Reference snippet for matching R `fixest` standard errors in `pyfixest`.

## Code Snippet
```python
import pyfixest as pf

fit = pf.feols(
    "log_wage ~ remote_post | worker_id + firm_id + cal_quarter",
    data=panel_df,
    vcov={"CRV1": "firm_id + cz_id"},
)
print(fit.tidy())
```

## Notes
- Always drop singleton fixed-effect observations before comparing degrees-of-freedom adjustments across R and Python.
- Clustering at both `firm_id` and commuting-zone `cz_id` accounts for spatial labor market shocks alongside employer policies.
- Use wild cluster bootstrap when the number of treated commuting zones in a subsample falls below 30.

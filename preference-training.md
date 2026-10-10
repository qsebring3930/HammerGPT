# Human preference loop

Round 1: `output/preference-round-001/comparison.png`. Five fresh procedural candidates passed independent geometry checks. Your previous statement that only candidate 2 was good is saved with the exact earlier layout identities. The current five await your choice and comments.

No neural graph checkpoint generated these radars. No preference training has occurred for this round. This is a proposal generator plus a trainable preference scorer, not a newly trained geometry generator.

When you choose a favorite, `preference_round.py review --best N --comments "your comments"` records four preferred-versus-other comparisons, combines them with the two prior explicit comparisons, and fits `preference_scorer.py`. The result is `preference-model.json`, an L2-regularized pairwise logistic scorer over thirteen measurable layout features. Comments remain verbatim design feedback; this numeric model does not learn their text.

For the following batch, pass `--model output/preference-round-001/preference-model.json` to `generate`, use a new seed range and output folder. It searches up to fifteen valid distinct proposals and selects four according to the fitted scorer plus one exploration proposal. The images omit model scores so you can judge the designs yourself.

This changes proposal selection. It does not update neural generator weights or architectural geometry rules. Six human comparisons will be a very small pilot: falling training loss would establish that the scorer fits your choices, not that it generalizes. Later batches supply independent human judgments. Keep a record of whether any candidate is acceptable, not just which weak candidate wins, and compare improvements before expanding the model.

Immediate review request: choose radar 1–5, explain what you like, and name the first changes you would make. “None are good” is also useful; it should not be forced into a positive preference label.

Nine relevant tests pass, covering geometry provenance/access, structural duplicate invariance, physical detours and preference direction. Five current candidates have saved individual audits. CS2 collision, vertical structure and competitive balance remain unverified.

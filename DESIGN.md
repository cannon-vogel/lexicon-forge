# Concept exploration and selection

## Concepts considered

1. **Vocabulary roguelike** — correct retrievals defeat enemies and advance rooms. Memorable, but failure-as-damage can punish productive mistakes and game state can compete with the learning task.
2. **Lexicon garden** — words grow as reviews mature. Good visualization of spacing, but the interaction risks becoming passive and collection-oriented.
3. **Semantic constellation** — connect related words into a graph. Excellent for exploration and synonym structure, but less efficient for exact cue→target retrieval.
4. **Confidence auction** — learners wager points on answers, training calibration. Interesting metacognition, but adds decision overhead to every trial.
5. **Escape-room clues** — solve word clues to unlock scenes. Strong narrative, but would require hundreds of authored contextual clues beyond what the source provides.
6. **Adaptive mastery campaign (“Lexicon Forge”)** — short runs built around retrieval, feedback, and spacing; game progression visualizes memory strength rather than replacing the learning task.

## Chosen concept: Lexicon Forge

Lexicon Forge won because the game loop and the learning loop are almost identical. The learner progresses by retrieving. A miss is information for the scheduler, not a lost life. Stable items become harder (typed recall) and less frequent. The exact 108-item test relationships remain a fully offline core deck, while the complete 537-term vocabulary list can be learned through lazily cached dictionary definitions.

### Core loop

1. **Attempt** before seeing the answer.
2. **Immediate feedback** after the attempt.
3. **Repair** missed/assisted items after a short lag in the same run.
4. **Expand spacing** after successful retrievals.
5. **Increase retrieval difficulty** from multiple-choice discrimination to typed generation as the item stabilizes.
6. **Reward delayed retrieval** with XP; never punish errors with lives or streak loss.

### Why not blanket interleaving?

Interleaving is useful in many category-learning domains, especially where discriminative contrast matters, but the 2019 meta-analysis by Brunmair & Richter found a *blocking advantage for word materials on average*. Therefore this design does not randomize every vocabulary item simply to claim an “interleaving” feature. It preserves the source test's local contrast sets while relying primarily on spacing and retrieval practice.

## Evidence base used for the design

- Dunlosky J, Rawson KA, Marsh EJ, Nathan MJ, Willingham DT. *Improving Students' Learning With Effective Learning Techniques* (2013). Practice testing and distributed practice received the review's highest utility ratings. DOI: 10.1177/1529100612453266.
- McDermott KB. *Practicing Retrieval Facilitates Learning* (Annual Review of Psychology, 2021). Review of retrieval-based learning across materials, ages, and classroom settings. DOI: 10.1146/annurev-psych-010419-051019.
- Kim SK, Webb S. *The Effects of Spaced Practice on Second Language Learning: A Meta-Analysis* (Language Learning, 2022). 48 experiments / 98 effect sizes; spacing showed medium-to-large benefits overall. DOI: 10.1111/lang.12479.
- Brunmair M, Richter T. *Similarity matters: A meta-analysis of interleaved learning and its moderators* (Psychological Bulletin, 2019). Overall interleaving benefit, but a blocking advantage for word materials; this is why the app does not indiscriminately interleave vocabulary. DOI: 10.1037/bul0000209.
- Sailer M, Homner L. *The Gamification of Learning: a Meta-analysis* (Educational Psychology Review, 2020). Small-to-moderate positive effects across cognitive, motivational, and behavioral outcomes; game elements are used here to support feedback and progress rather than replace retrieval.
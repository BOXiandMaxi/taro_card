# Tarot rules

The deck has 22 Major Arcana and 56 Minor Arcana across Wands, Cups, Swords and Pentacles. Draws are server authoritative, without replacement, and use a cryptographic random source. All cards are drawn upright by default. When `REVERSED_CARDS_ENABLED` is true, each drawn card independently has a 50% chance of being reversed. The server stores the orientation at draw time and uses it to choose the revealed keywords and description, even if the setting later changes.

Default 3-card positions: current situation, main obstacle/influence, guidance. Default 5-card positions: current situation, root cause, main obstacle, strengths/resources, guidance/direction. The 10-card spread is a documented Celtic Cross variant: present, crossing influence, conscious aim, foundation, recent past, near future, self, environment, hopes/fears, potential direction.

Alternate 3-card and 5-card spreads may be added as seeded spread records. A question may recommend a spread, but visitors may always choose any length. Interpretations describe reflection and possibilities, never certain futures or professional medical, legal, or financial advice.

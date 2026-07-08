# Codex-regler for DG

## Grundprinciper

- Vi kan kora pa svenska.
- Det har ar ett Pygame-projekt for ett dartspel och statistiken ar framst for att det ar kul.
- Programmet behover inte skydda mot alla felaktiga inmatningar. Om spelaren skriver fel far spelaren skylla sig sjalv.
- Spelet far lita pa spelarna. Det ar okej att 501 inte tekniskt tvingar dubbel ut, sa lange anvandaren matar in riktiga kast.
- Skapa inte nya filer eller mappar utan att fraga forst, om inte anvandaren uttryckligen har bett om det.

## Statistik

- Statistik sparas bara for markerade spelare, till exempel Axel med `*` och Eila med `/`.
- Vanliga spelare i entertainment-systemet behover ingen statistik.
- I 501 far man fraga om antal utgangspilar efter att en spelare gatt ut, till exempel om spelaren star pa 40 och skriver 40.
- Dubbelforsok kan anges manuellt med suffix, till exempel `20.2`, `0.1` eller `40.3`.
- Om spelaren star pa 170 och traffar 145 efter missad bull i 25:an skrivs det som `145.1`.
- Utan suffix ska programmet inte anta att ett vanligt inskrivet resultat inneholl ett bull- eller dubbelforsok.
- Om dubbelforsok eller poang skrivs fel ar det anvandarens ansvar. Statistikens exakthet bygger pa att man matar in rimliga varden.

## Klockan

- Klockan ska anvanda exakt pilsekvens per runda, till exempel `101`, `111`, `11`.
- Nar en spelare ar markerad ska Klockan darfor kunna ge battre statistik med 0/1 per pil.
- Markera statistikspelare fran start om Klockan-statistiken ska bli komplett.
- For omarkerade vanliga spelare racker enkel input, eftersom deras statistik inte spelar roll.

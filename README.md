#HADES 2.0 fuer Codex

HADES ergaenzt Codex um kostenbewusste Delegation: Tools vor Modellen,
Luna fuer schmale Aufgaben, Sol fuer Implementierung, Astra fuer Planung
und schwierige Entscheidungen. Qualitaet und nachgewiesene Fertigstellung
haben Vorrang vor Tokenersparnis.

**Du nutzt weiterhin Codex mit deiner ChatGPT-Abo-Anmeldung.**
Kein API-Key, eigener API-Client, Copilot SDK oder zusaetzlicher Dienst ist
noetig. Subagenten verbrauchen ebenfalls dein Codex-Kontingent; HADES macht
die Nutzung weder unbegrenzt noch garantiert billiger.

## Start in Codex

1. Oeffne **dieses Repository bzw. diesen Worktree** in einem aktuellen
   lokalen Codex-Client (App, IDE-Erweiterung oder CLI).
2. Melde dich mit **Sign in with ChatGPT** an, nicht mit einem API-Key.
   In der CLI zeigt `codex login status` die Anmeldemethode.
3. Vertraue dem Projekt nach Pruefung der Konfiguration. Codex laedt
   projektlokale Konfiguration nur fuer vertrauenswuerdige Projekte.
4. Starte eine neue Codex-Unterhaltung. HADES gilt durch
   [AGENTS.md](AGENTS.md) automatisch; **BALANCED** ist die Vorgabe.
5. Beschreibe deine Aufgabe ganz normal, etwa:

   ```text
   Implementiere die erste Funktion fuer braincloner_AI.
   Klaere offene Produktentscheidungen zuerst und teste das Ergebnis.
   ```

Explizit geht auch `$hades <Aufgabe>`. In der CLI kannst du mit `/skills`
die Skill-Erkennung und mit `/agent` gestartete Agenten pruefen. Nicht
jede Aufgabe braucht einen Subagenten.

Die aktuelle Unterhaltung muss dafuer tatsaechlich in **Codex** laufen:
Diese Dateien stellen eine Copilot-Unterhaltung nicht auf Codex um.
Es werden weder deine globale Konfiguration noch Anmeldedaten geaendert.

## Rollen und Modelle

| Rolle | Modell | Aufgabe |
| --- | --- | --- |
| Hauptchat | Deine bestehende Codex-Modellwahl | Nutzerkontakt, leichte Koordination, Tools |
| `hades_astra` | `gpt-6-astra`, high | Einmaliger Plan bei komplexer Arbeit, Architektur, Eskalation |
| `hades_sol` | `gpt-5.6-sol`, medium | Implementierung, Debugging, anspruchsvolle Pruefung |
| `hades_luna` | `gpt-5.6-luna`, low | Enge, klar spezifizierte Teilaufgaben, keine weitere Delegation |

Die Modellnamen stammen aus der Vorlage. Ihre Verfuegbarkeit haengt von
deinem Abo, Rollout und Client ab. Pruefe die Auswahl in Codex (`/model`
in der CLI). Bei einem nicht verfuegbaren Modell **stoppen und die
betroffene Rollendatei bewusst anpassen**, statt heimlich auf eine API
oder ein anderes Modell auszuweichen.

Die Rollen liegen unter [.codex/agents](.codex/agents).
Der Hauptchat wird absichtlich nicht auf Astra festgelegt: Eine Skill
kann dessen Modell nicht nach der Planung automatisch abschalten.
Fuer niedrigeren Grundverbrauch kannst du im Hauptchat Sol waehlen;
Astra wird dann nur fuer begruendete Planungs- oder Eskalationsaufgaben
aufgerufen. Nach einem Astra-Ergebnis geht die Ausfuehrung zurueck an
den Hauptchat bzw. Sol/Luna.

## Aufbau

| Datei | Zweck |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Kleine, automatisch geladene Projektregeln |
| [.agents/skills/hades/SKILL.md](.agents/skills/hades/SKILL.md) | Nativ auffindbare Codex-Skill |
| [.hades/HADES_ORCHESTRATOR.md](.hades/HADES_ORCHESTRATOR.md) | Nur bei Bedarf geladene Orchestrierungsregeln |
| [.codex/config.toml](.codex/config.toml) | Native Agentenlimits und ChatGPT-Anmeldung |
| [.codex/agents](.codex/agents) | Schlanke, eigenstaendige Rollen-Prompts |
| [.hades/config.json](.hades/config.json) | HADES-Policy mit ECO, BALANCED und MAX |
| [.hades/templates](.hades/templates) | Context Capsule, Result Packet, Failure Packet, Shared State |
| [.hades/state.py](.hades/state.py) | Lokale Initialisierung und deterministische Vertrags-/DAG-Pruefung |

`ECO`, `BALANCED` und `MAX` sind **HADES-Policies**, keine Codex-CLI-Profile.
Zum Wechseln genuegt beispielsweise `Nutze HADES ECO fuer diese Aufgabe`.
ECO bevorzugt schmale Luna-Auftraege, MAX startet modellpflichtige Arbeit
haeufiger bei Sol. Alle Profile behalten dieselbe Qualitaetsuntergrenze:
hohes Risiko erfordert Tests plus Sol-Review, kritische Arbeit Tests plus
Sol/Astra-Verifikation. Keine erfundenen Erfolgsquoten oder Preisangaben.

## Shared State und Ausgabepruefung

Fuer mehrstufige Arbeit legt der Koordinator einen frischen Lauf an:

```sh
python3 .hades/state.py init \
  --goal "Eine klar abgegrenzte Funktion implementieren" \
  --success "Akzeptanzkriterien sind mit Belegen erfuellt" \
  --success "Relevante vorhandene Tests bestehen"
```

Die Ausgabe ist der Pfad zu `.hades/runs/<eindeutige-id>/state.json`.
Diese lokalen, Git-ignorierten Dateien sind kein Tagebuch. Sie enthalten
nur Anforderungen, DAG, bestaetigte Fakten, Ergebnisse und offene Probleme.
Kein globaler `current`-Zeiger: Unabhaengige Aufgaben erhalten getrennte
Laeufe. Nur der jeweilige Koordinator aendert den State; Worker liefern
Resultate in eindeutig zugewiesenen Dateien.

```sh
python3 .hades/state.py validate state .hades/runs/<id>/state.json
python3 .hades/state.py validate capsule <capsule.json>
python3 .hades/state.py validate result <result.json>
python3 .hades/state.py validate failure <failure.json>
```

Die JSON-Vorlagen sind absichtlich unvollstaendige **Ausfuellvorlagen**.
Leere Ziele, unbekannte Felder, ungueltige Statuswerte, zyklische oder
unbekannte Abhaengigkeiten und unbelegte Erfolgsmeldungen werden abgelehnt.
`validate` liest nur und fuehrt keine Befehle aus den Paketen aus.
Ein abgeschlossener Lauf braucht erfolgreiche DAG-Knoten, belegte
Akzeptanzkriterien, keine offenen Probleme und einen
`current_test_state` von `passed` oder begruendet `not_applicable`.
`passed` setzt tatsaechlich eingetragene, bestandene Checks voraus;
`not_applicable` ist fuer Aufgaben ohne Testbefehle, nicht fuer fehlende
Testwerkzeuge oder uebersprungene Pflichtpruefungen.

Voraussetzung fuer das optionale State-Werkzeug: Python 3.11 oder neuer.
Keine externen Python-Pakete. Ohne Python funktionieren die nativen
Rollen weiterhin; die deterministische Paketpruefung ist dann jedoch
blockiert und muss als solche benannt werden.

## Was technisch erzwungen wird - und was nicht

- Codex liest die Rollen und Modellkonfiguration nativ. Die Projektvorgabe
  ist ChatGPT-Anmeldung; persoenliche/CLI-Overrides und verwaltete Policies
  koennen Vorrang haben. Pruefe deshalb die tatsaechliche Anmeldung.
- Die Konfiguration begrenzt offene Subagenten auf neun. Bereits gesetzte
  V2-spezifische oder explizite Laufzeit-Overrides koennen dieses Limit
  uebersteuern. `max_depth = 2` gilt technisch nur fuer Codex V1.
- Maximal drei Sol- und sechs Luna-Agenten, die Rollen-Hierarchie,
  einmalige Planung, eine korrigierte Wiederholung und risikobasierte
  Reviews sind **Agentenanweisungen**, keine separate Scheduler-Engine.
  Bei V2 ist auch die Tiefe eine Policy.
- Der Koordinator muss den Validator vor Ergebnisuebernahme/Fertigmeldung
  aufrufen. Er prueft Struktur und Konsistenz, nicht die Wahrheit eines
  Testbelegs. Ein JSON-Erfolg ersetzt keinen tatsaechlich ausgefuehrten Test.
- Kapseln begrenzen den bewusst uebergebenen Kontext. Von Codex geerbte
  Projektregeln/Systemkontexte sind damit nicht garantiert ausgeschlossen.
  Keine Chat-Historie weiterreichen: Wenn angeboten, `fork_turns="none"`
  bzw. `fork_context=false` explizit setzen. Bei aktuellen V2-Clients kann
  Weglassen die gesamte Historie und das Elternmodell uebernehmen.
- Output-Budgets und Expected-Cost-Routing sind Vorgaben, keine harten
  Tokenlimits oder gemessenen Kostenschaetzungen. Erforderlichen Code
  nicht abschneiden. Prompt-Caching ist vom Anbieter abhaengig.
- Sandbox, Freigaben und Netzwerkrechte werden **nicht gelockert**.
  Projektdateien koennen Kontoberechtigungen nicht erweitern.

## Pruefung

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

Die lokalen Tests pruefen Konfiguration, Rollenverknuepfung, Profile,
Pakete, DAG-Abhaengigkeiten, Fehlerfaelle und persistente Laufanlage.
Die native Projektkonfiguration und Skill-Erkennung wurden ausserdem
mit Codex CLI **0.153.4** isoliert und ohne Anmeldung geprueft.
Ein echter Modellaufruf braucht zusaetzlich deinen angemeldeten
Codex-Client. Als manueller Smoke-Test:

```text
$hades Starte genau einen hades_luna-Agenten mit dem Auftrag, die
erste Ueberschrift aus README.md zu nennen. Keine Dateien aendern,
keine weiteren Agenten starten. Warte auf sein Ergebnis und melde
die Ueberschrift. Stoppe bei einem Anmelde- oder Modellfehler.
```

Dabei einmal pruefen, dass die Rolle erscheint, keine API-Anmeldung
verwendet wird und ein echtes Ergebnis zurueckkommt. Dieser bewusst
explizite Delegationstest ist kein Muster fuer jede kleine Aufgabe.

## Offizielle Referenzen

- [Codex-Anmeldung und Abo/API-Unterschied](https://developers.openai.com/codex/auth)
- [Native Subagenten und Rollen](https://developers.openai.com/codex/multi-agent)
- [Skills und automatische Erkennung](https://developers.openai.com/codex/skills)
- [Konfigurationsreferenz](https://developers.openai.com/codex/config-reference)
- [Modellverfuegbarkeit](https://developers.openai.com/codex/models)

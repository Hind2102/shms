---
title: SHMS – Site Hazard Management (demo)
emoji: 🦺
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: agpl-3.0
short_description: AI-assisted hazard reporting – public course demo
---

# SHMS – Site Hazard Management System (public demo)

Course project demo: report an unsafe condition or missing PPE from a photo, see the AI's suggestions (YOLOv8s
trained on SH17, running on CPU), confirm them, and follow the case through the workflow and the site map.

**Public demo – do not upload confidential, personal or site photos; data resets on restart.**

- Open the app directly at **https://hind2102-shms-demo.hf.space**. Sign-in and "Use my current location" do not
  work inside the embedded frame on this page.
- Demo accounts (password for all: `shms-demo-2026`, a documented demo value): `ahmed` (reporter), `khalid` (Area
  Owner), `sara` (safety supervisor), `yousef` (manager, read-only).
- Everything shown is synthesized. Anything you add is deleted when the Space restarts or goes to sleep.

Source code, evaluation and limits: see the project repository. The AI is a suggestion aid with known weaknesses
(failed external validation for hard hats); every suggestion is confirmed by a person.

Model weights: SH17 YOLOv8s from the dataset authors' release (github.com/ahmadmughees/SH17dataset, release v1),
downloaded at build time for non-commercial academic use; not redistributed here. Code licence: AGPL-3.0.

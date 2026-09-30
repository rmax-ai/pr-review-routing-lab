# Mock protocol demonstration

This is a mechanics demonstration over simulated fixtures. It does not claim model quality, calibration quality, real cost savings, autonomy, or reviewer independence.

**Table (backend=mock; source=simulated; n=70; simulated).**
| case | architecture | route | terminal | backend |
|---|---|---|---|---|
| c01 | A0 | human_review | routed_human | mock |
| c01 | A1 | accept | sol_complete_accept | mock |
| c01 | A2 | human_review | routed_human | mock |
| c01 | A3 | accept | sol_complete_accept | mock |
| c01 | A4 | accept_no_sol | accept_no_sol | mock |
| c01 | A5 | accept_no_sol | accept_no_sol | mock |
| c01 | dual | accept_no_sol | accept_no_sol | mock |
| c02 | A0 | deterministic_reject | det_rejected | mock |
| c02 | A1 | deterministic_reject | det_rejected | mock |
| c02 | A2 | deterministic_reject | det_rejected | mock |
| c02 | A3 | deterministic_reject | det_rejected | mock |
| c02 | A4 | deterministic_reject | det_rejected | mock |
| c02 | A5 | deterministic_reject | det_rejected | mock |
| c02 | dual | deterministic_reject | det_rejected | mock |
| c03 | A0 | human_review | routed_human | mock |
| c03 | A1 | changes_required | sol_complete_changes_required | mock |
| c03 | A2 | human_review | routed_human | mock |
| c03 | A3 | remediate_simulated | routed_remediate_simulated | mock |
| c03 | A4 | accept_no_sol | accept_no_sol | mock |
| c03 | A5 | accept_no_sol | accept_no_sol | mock |
| c03 | dual | accept_no_sol | accept_no_sol | mock |
| c04 | A0 | human_review | routed_human | mock |
| c04 | A1 | changes_required | sol_complete_changes_required | mock |
| c04 | A2 | human_review | routed_human | mock |
| c04 | A3 | remediate_simulated | routed_remediate_simulated | mock |
| c04 | A4 | remediate_simulated | routed_remediate_simulated | mock |
| c04 | A5 | remediate_simulated | routed_remediate_simulated | mock |
| c04 | dual | remediate_simulated | routed_remediate_simulated | mock |
| c05 | A0 | human_review | routed_human | mock |
| c05 | A1 | changes_required | sol_complete_changes_required | mock |
| c05 | A2 | human_review | routed_human | mock |
| c05 | A3 | remediate_simulated | routed_remediate_simulated | mock |
| c05 | A4 | remediate_simulated | routed_remediate_simulated | mock |
| c05 | A5 | remediate_simulated | routed_remediate_simulated | mock |
| c05 | dual | remediate_simulated | routed_remediate_simulated | mock |
| c06a | A0 | human_review | routed_human | mock |
| c06a | A1 | changes_required | sol_complete_changes_required | mock |
| c06a | A2 | human_review | routed_human | mock |
| c06a | A3 | remediate_simulated | routed_remediate_simulated | mock |
| c06a | A4 | remediate_simulated | routed_remediate_simulated | mock |
| c06a | A5 | remediate_simulated | routed_remediate_simulated | mock |
| c06a | dual | remediate_simulated | routed_remediate_simulated | mock |
| c06b | A0 | human_review | routed_human | mock |
| c06b | A1 | accept | sol_complete_accept | mock |
| c06b | A2 | human_review | routed_human | mock |
| c06b | A3 | accept | sol_complete_accept | mock |
| c06b | A4 | accept_no_sol | accept_no_sol | mock |
| c06b | A5 | accept_no_sol | accept_no_sol | mock |
| c06b | dual | accept_no_sol | accept_no_sol | mock |
| c07 | A0 | human_review | routed_human | mock |
| c07 | A1 | human_review | routed_human | mock |
| c07 | A2 | human_review | routed_human | mock |
| c07 | A3 | human_review | routed_human | mock |
| c07 | A4 | human_review | routed_human | mock |
| c07 | A5 | human_review | routed_human | mock |
| c07 | dual | human_review | routed_human | mock |
| c08 | A0 | human_review | routed_human | mock |
| c08 | A1 | accept | sol_complete_accept | mock |
| c08 | A2 | human_review | routed_human | mock |
| c08 | A3 | accept | sol_complete_accept | mock |
| c08 | A4 | accept_no_sol | accept_no_sol | mock |
| c08 | A5 | accept_no_sol | accept_no_sol | mock |
| c08 | dual | accept_no_sol | accept_no_sol | mock |
| c09 | A0 | human_review | routed_human | mock |
| c09 | A1 | changes_required | sol_complete_changes_required | mock |
| c09 | A2 | human_review | routed_human | mock |
| c09 | A3 | remediate_simulated | routed_remediate_simulated | mock |
| c09 | A4 | remediate_simulated | routed_remediate_simulated | mock |
| c09 | A5 | remediate_simulated | routed_remediate_simulated | mock |
| c09 | dual | remediate_simulated | routed_remediate_simulated | mock |

## State-transition table

**Table (backend=mock; source=simulated; n=7; simulated).**
| transition | terminal |
|---|---|
| deterministic fail | det_rejected |
| Gate A no-Sol | accept_no_sol |
| Sol accepts | sol_complete_accept |
| Sol requests changes | sol_complete_changes_required |
| simulated remediation route | routed_remediate_simulated |
| human route | routed_human |
| error | error_terminal |

## Case × arm traces

**Table (backend=mock; source=simulated; n=70; simulated).**
| case | arm | stages | decision digest |
|---|---|---|---|
| c01 | A0 | deterministic_gates, human_review | b9d57cc7717f92bfe52b9ba29566914354dd5472152a354467ce4616a7a38fec |
| c01 | A1 | deterministic_gates, sol_review | 17a350642c448cd058e378b7b62a475bfa5c82dce978b9d40dfb2febf7bc5b9f |
| c01 | A2 | deterministic_gates, gate_a, human_review | 52c09695f2ad3aceba2c26a9453c71516d7634666d62007b64ad2f1f73862179 |
| c01 | A3 | deterministic_gates, sol_review, gate_b | 7c68202adf5c3279f82dc9d7314567b7f8b947b71877bb4de28e4f16f385858b |
| c01 | A4 | deterministic_gates, gate_a | fca8e1b3a8ef635a34e318afff71bdb7cf1ae96d7137ff81f3457c0d7a88a729 |
| c01 | A5 | deterministic_gates, gate_a | c73455a262a97c4e19b0c7ed5787cf524091921797440774cacba12d94d2a08e |
| c01 | dual | deterministic_gates, gate_a | 0295ce44e5b7707a2e839b4c0d0a02cdb8b9f6d5a08b802737d62bda09cd5ccd |
| c02 | A0 | deterministic_gates | 6a0effa8e10d4aced1a008a1da0207bdd1603c582fab901d49ec6d60262062f8 |
| c02 | A1 | deterministic_gates | 2f2f4f6404f96b1ce0bf8f4f6190c7e336247eea0a00160f9881501e5386e257 |
| c02 | A2 | deterministic_gates | 96c9ff4e4e637ee7d3f7ef9dcdf6ce50f409d401de9ed42c99d49dcc69913a26 |
| c02 | A3 | deterministic_gates | c300e531651977190a7af3ada45569efd3fa394c6e04693ed05bd666e1d5524a |
| c02 | A4 | deterministic_gates | a159f2986d2afee679bc10a14b48c1839a6e5a4c9dc974a34b3d09ab498e98d2 |
| c02 | A5 | deterministic_gates | cfab8d9c81ac36b8f96c804213eebf8f52c32be0eb41312d07c95193b4785f9a |
| c02 | dual | deterministic_gates | dd444dcf3db9d695a375f00565be220b41dde23826acdee1c077d34cda5e19fa |
| c03 | A0 | deterministic_gates, human_review | e810f3345a8e2f858714f7ddfbfd6a0e83ae4b22c8f23f7272488e5b4e46840d |
| c03 | A1 | deterministic_gates, sol_review | 4847e45287c502ae024fb5597300f4238376b76ee1a25304b470960cad1e3282 |
| c03 | A2 | deterministic_gates, gate_a, human_review | b82a0ca15c54fb5b3944933210245daa1c16527463bb400b82ae384cf18dc2e7 |
| c03 | A3 | deterministic_gates, sol_review, gate_b | dc7d7522e96897576770ffc1ff775c38a7103c0db4c100afaa6a5f904ea07c98 |
| c03 | A4 | deterministic_gates, gate_a | 9dc9f4ad9af3f1b681cdb522d2a4215f4705f8ee8613a1215f04a93e153809fc |
| c03 | A5 | deterministic_gates, gate_a | 48720d467ac7b42950cdcc928e496b511a5b02cf2a8b5c8f4c568f74421cf5fc |
| c03 | dual | deterministic_gates, gate_a | 78123369d4403b766f30e0aa60fac6d05ed657d290ff2403115637cec5263616 |
| c04 | A0 | deterministic_gates, human_review | 36b86827e1953c1a3a2e2c042ab29d90f3ad0fdc0e6b279c0f107db33d749cab |
| c04 | A1 | deterministic_gates, sol_review | c4ca694b897b677c4afaa8f728ce33a852dc95a6dd20699a7e4ebdcd614d8fc7 |
| c04 | A2 | deterministic_gates, gate_a, sol_review, human_review | 3aa239bd48611c51aa631c07bd20864910a0a7cc1d5497899ede101a408c5e2d |
| c04 | A3 | deterministic_gates, sol_review, gate_b | 65f3b31a104278cbda484be5f7b147c88f805f9761d32694c03c3d915c514f46 |
| c04 | A4 | deterministic_gates, gate_a, sol_review, gate_b | 82efe7c440fc6b7755931d696d828f306410046c0c2ea976d8a46ce3a7adcec3 |
| c04 | A5 | deterministic_gates, gate_a, sol_review, gate_b | bf7fed20e76188f742bc2f6b533e842842643b514b5f11c046eadcec2daac75c |
| c04 | dual | deterministic_gates, gate_a, sol_review, dual_review, gate_b | f6114ab5fcba912d4f8d8651fc3205dc1326e151cea44c21ca88168b31a3c33d |
| c05 | A0 | deterministic_gates, human_review | 07041e3c269fb235034858c5f8738b26bf91098ae156941409d8e9548ffe5a4f |
| c05 | A1 | deterministic_gates, sol_review | 104cece2517f6d80059671426b950036120f23812aff4f872577f7400e73692e |
| c05 | A2 | deterministic_gates, gate_a, sol_review, human_review | 4a115d8abe137a0a395fcbd93eb561439d219b79d6dd0c1a411cde0f5ec05401 |
| c05 | A3 | deterministic_gates, sol_review, gate_b | 8ef1d0fd23944636ce278ec6f3014d5686df6ca0bf7dfc8dfc3e9f40bb415256 |
| c05 | A4 | deterministic_gates, gate_a, sol_review, gate_b | 8e165c72b5cc9f43c4aa4bf92f0fc87171e7f51dedc12f4d8235fa26d75605d2 |
| c05 | A5 | deterministic_gates, gate_a, sol_review, gate_b | 257dfbef45cfa26372d0c2ff6799f271f432e40d5a962d818d1af8aefe84a97c |
| c05 | dual | deterministic_gates, gate_a, sol_review, gate_b | ba3820c85c9034ec0d1c2989d4aa2710366d584f6a13456784c1f1704d1eaf35 |
| c06a | A0 | deterministic_gates, human_review | 678574f12ee3db8aa47ea04db7f333d81a58a33dc8be1cc9d20b9dffcae8cfc9 |
| c06a | A1 | deterministic_gates, sol_review | 9fec304272b3f03b48c24e4493d85d797b8e4b757c5adc4d815852e021b7b22b |
| c06a | A2 | deterministic_gates, gate_a, sol_review, human_review | a22f0a6df85ce197f59fc10906cb939d46beef5852676062c7690c6e1f7fac32 |
| c06a | A3 | deterministic_gates, sol_review, gate_b, remediation_loop | d979544013e2d63e8de69821b07adc76f03705ecc18df97e7a82bed0f520f6e0 |
| c06a | A4 | deterministic_gates, gate_a, sol_review, gate_b, remediation_loop | fbc5bd165789813c73837acd23a90d42076090e80df5c41f353e403abec37e0b |
| c06a | A5 | deterministic_gates, gate_a, sol_review, gate_b, remediation_loop | 63ea1df31f5f38f3f6ad6aca4294a7fe8ae29b1abd861790446a92aebaacace0 |
| c06a | dual | deterministic_gates, gate_a, sol_review, gate_b, remediation_loop | b8dabdde39cf348d9f4a776a531075a669bea4fc88c0222a593afcd58b51411b |
| c06b | A0 | deterministic_gates, human_review | 3d732aec0e64583720899b44dff31e9105fdd576c76ab6f736f5dccb16a3c4e5 |
| c06b | A1 | deterministic_gates, sol_review | 56096fb3527bf8677a64ff9840f8500f078c37808bd4b557f0ea7b6a5a7aed58 |
| c06b | A2 | deterministic_gates, gate_a, human_review | 491f67e5e29d22ab93f31b2401c1105ecbe90b812cfe087e44e6d76a07a5a024 |
| c06b | A3 | deterministic_gates, sol_review, gate_b | 1e89962591ba98f09d0836404cede0411e53e2040c1af2163ece310e2300717c |
| c06b | A4 | deterministic_gates, gate_a | ad59a2c8c41f0c98c52775cad0ac0d1c922ca255c07d25af850adeae8d9b02dc |
| c06b | A5 | deterministic_gates, gate_a | 8cfe494d1dc1e95fa1f16381c36641d141cbd1c9f00e46aea9a0629a65bd7e9a |
| c06b | dual | deterministic_gates, gate_a | 07555e93637dd8be3590ed0485a25a0147b0ca72b52ecaf15fd642d31a0c2c09 |
| c07 | A0 | deterministic_gates, human_review | 3f2f1ab308955bcedec6ccd88d0bc60a7e7248e0c4fa3e313e9cac03f435492d |
| c07 | A1 | deterministic_gates, sol_review, human_review | bc38f3c10ec8ad1a3df3a192338935fccab197e781cb899e00c9ea0bbefdf43a |
| c07 | A2 | deterministic_gates, gate_a, sol_review, human_review | ee966eec2cbef777ec20ff268f5c03aa3b5c323b1ebd693446b9cf1bec3455d1 |
| c07 | A3 | deterministic_gates, sol_review, gate_b, human_review | 78c399d59143c88cae9c8dab433858a99253aeb7ed3330501a8895ee78759792 |
| c07 | A4 | deterministic_gates, gate_a, sol_review, gate_b, human_review | 20066a2a007371d4752830aa761abf5b86276701649a024ff373ebbb2ea43042 |
| c07 | A5 | deterministic_gates, gate_a, sol_review, gate_b, human_review | 9f2b87cc8e8e329778dcdc60075084e461e9d3e63a6725fc3d3baf9c48fc675e |
| c07 | dual | deterministic_gates, gate_a, sol_review, dual_review, gate_b, human_review | 2f8bf1e416a676451eb63aec2907e39392b9bffcec8116c325f31fb970598973 |
| c08 | A0 | deterministic_gates, human_review | 168e7a5c3400a5e30af5c26a434938db6fcc7ab1d907e3758cbde30f4deb8751 |
| c08 | A1 | deterministic_gates, sol_review | d67b771379c247343d288671350dac95e894c7596c859e2974acd6fb440140e5 |
| c08 | A2 | deterministic_gates, gate_a, human_review | a7765829de865912990e759bb4dc8b08335deed0b8def0535bad865bf919fc2a |
| c08 | A3 | deterministic_gates, sol_review, gate_b | fa7a931004b7b2adf0b4a6274f9069e2a0b015a7e198ce4a3b0e8c32c134f52e |
| c08 | A4 | deterministic_gates, gate_a | 2ba0bb779d7394999d1a49064864e50d0ddda0a9315eb2b3528bffb35755bbfb |
| c08 | A5 | deterministic_gates, gate_a | f6eb1f7f01c334a0325fddd8059eec108191251ab90b2c61194b276f8df6da81 |
| c08 | dual | deterministic_gates, gate_a | e7be4227ad5570f08fd18cef87b9bbb0b40a803ead539f57214d3f994a97426e |
| c09 | A0 | deterministic_gates, human_review | d4092761ae7f1660cea2759634f73b0b41977d67c4005d715c790024fa4aa81e |
| c09 | A1 | deterministic_gates, sol_review | 18556f5447ce8fd3f3f755dc1d2b88392422e0a6c28546c932a8025e0cb0363a |
| c09 | A2 | deterministic_gates, gate_a, sol_review, human_review | b434ec39ed9028d4f99cbaa588ec10f642bff16de9e31dbd74d1f72feb9cfa40 |
| c09 | A3 | deterministic_gates, sol_review, gate_b | 4f5778397541ab0903b58edbbeb21c37b8c2869eab7542d216eec473b7f424a3 |
| c09 | A4 | deterministic_gates, gate_a, sol_review, gate_b | d3398d4ecafd653df5054a252e9c86301dd2603f258b758b7b894d568b6a8f96 |
| c09 | A5 | deterministic_gates, gate_a, sol_review, gate_b | 08d88884abb555ac3c469563cd1354efce7e9c309378cf56a52ba02a191a0f49 |
| c09 | dual | deterministic_gates, gate_a, sol_review, dual_review, gate_b | b168912a306f9b66aba0e2c7d228482f7ce6d8a925fd169f119594cddecdcd7b |

## Metric-registry coverage

**Table (backend=mock; source=simulated; n=37; simulated).**
| metric | population | numerator | denominator | numerator_value | denominator_value | source | value | unavailable_reason |
|---|---|---|---|---|---|---|---|---|
| blocker_recall | expected_blockers | matched_blockers | expected_blockers | None | None | score | None | None |
| blocker_recall_simulated | expected_blockers | matched_blockers | expected_blockers | 0 | 0 | score | None | None |
| cost_per_blocker | matched_blockers | total_cost | matched_blockers | None | 0 | costing | None | no_available_usage |
| cost_per_material_finding | matched_material_findings | total_cost | matched_material_findings | None | 0 | costing | None | no_available_usage |
| cost_per_pr | measured_cases | total_cost | measured_cases | None | None | costing | None | no_available_usage |
| cost_per_pr_simulated | simulated_cases | total_cost | simulated_cases | None | None | costing | None | no_available_usage |
| error_rows_skipped | run_rows | error_rows | run_rows | 0 | 70 | run | 0 | None |
| gate_a_false_safe_rate | gate_a_no_sol | gold_risky_no_sol | gate_a_no_sol | 3 | 12 | gold | 0.25 | None |
| gate_b_false_no_human_rate | gate_b_nonhuman | gold_human_required_nonhuman | gate_b_nonhuman | 0 | 20 | gold | 0.0 | None |
| human_avoidance_rate | eligible_cases | cases_without_human | eligible_cases | 40 | 63 | run | 0.6349206349206349 | None |
| jev_calls_per_pr | cases | jev_calls | cases | 60 | 70 | run | 0.8571428571428571 | None |
| latency_p50_overall | cases | p50_latency_ms | cases | None | None | observation | 0.0 | None |
| latency_p50_per_stage | stage_observations | p50_stage_latency_ms | stage_observations | None | None | observation | 0.0 | None |
| latency_p95_overall | cases | p95_latency_ms | cases | None | None | observation | 0.0 | None |
| latency_p95_per_stage | stage_observations | p95_stage_latency_ms | stage_observations | None | None | observation | 0.0 | None |
| material_recall_including_blocker | expected_material_and_blocker | matched_material_and_blocker | expected_material_and_blocker | None | None | score | None | None |
| material_recall_including_blocker_simulated | expected_material_and_blocker | matched_material_and_blocker | expected_material_and_blocker | 26 | 26 | score | 1.0 | None |
| material_recall_only | expected_material | matched_material | expected_material | None | None | score | None | None |
| material_recall_only_simulated | expected_material | matched_material | expected_material | 26 | 26 | score | 1.0 | None |
| overcall_rate | produced_findings | unmatched_findings | produced_findings | None | None | score | None | None |
| overcall_rate_simulated | produced_findings | unmatched_findings | produced_findings | 0 | 26 | score | 0.0 | None |
| remediation_eligibility_rate | review_cases | simulated_remediation_routes | review_cases | 17 | 63 | run | 0.2698412698412698 | None |
| required_but_unmentioned | required_requirements | uncited_requirements | required_requirements | None | None | score | None | None |
| required_but_unmentioned_simulated | required_requirements | uncited_requirements | required_requirements | 6 | 32 | score | 6 | None |
| requirement_coverage_recall | cited_expected_requirements | independently_covered | cited_expected_requirements | None | None | score | None | None |
| requirement_coverage_recall_simulated | cited_expected_requirements | independently_covered | cited_expected_requirements | 26 | 26 | score | 1.0 | None |
| review_loops | linked_fixed_head_rows | real_re_review_artifacts | linked_fixed_head_rows | 0 | 7 | artifact | 0.0 | None |
| review_loops_simulated | linked_fixed_head_rows | simulated_re_review_artifacts | linked_fixed_head_rows | 4 | 7 | artifact | 0.5714285714285714 | None |
| severity_exactness_rate | matched_findings | exact_severity_matches | matched_findings | None | None | score | None | None |
| severity_exactness_rate_simulated | matched_findings | exact_severity_matches | matched_findings | 26 | 26 | score | 1.0 | None |
| sol_avoidance_rate | eligible_cases | cases_without_sol | eligible_cases | 25 | 63 | run | 0.3968253968253968 | None |
| sol_calls_per_pr | cases | sol_calls | cases | 41 | 70 | run | 0.5857142857142857 | None |
| spurious_blocker_rate | produced_findings | unmatched_blockers | produced_findings | None | None | score | None | None |
| spurious_blocker_rate_simulated | produced_findings | unmatched_blockers | produced_findings | 0 | 26 | score | 0.0 | None |
| throughput | completed_cases | cases | elapsed_wall_time | None | None | observation | None | None |
| tokens | measured_cases | input_plus_output_tokens | measured_cases | None | None | usage | None | no_available_usage |
| tokens_simulated | simulated_cases | input_plus_output_tokens | simulated_cases | None | None | usage | None | no_available_usage |

## No-claims section

- Mock values are simulated mechanics drivers, not measured model outcomes.
- This report makes no model-quality or calibration-quality claim.
- Costs are not real savings and remediation is not autonomous.
- A5 and dual reviewer lanes are wiring simulations, not independence claims.

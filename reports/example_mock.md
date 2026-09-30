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
| c01 | A0 | deterministic_gates, human_review | 2521e22416f69c5cd5c2a8b9ffea52fd11fb245c6f0d28d58d2c18c5acb1c6bb |
| c01 | A1 | deterministic_gates, sol_review | ffe08d7062b1a3f6b47ccddf0a3f18e4729b5a45254315c3e7c6fecde1c1eb0f |
| c01 | A2 | deterministic_gates, gate_a, human_review | eb1febb828bb153d7a8c289ebff9bc4a4001889173901acaf1b8082c82b49114 |
| c01 | A3 | deterministic_gates, sol_review, gate_b | f846194cb27aadf17d96ccff231b0ce43f7d8216c9bcaa144d9fcebde07c515c |
| c01 | A4 | deterministic_gates, gate_a | 76f5f8fc3298b06c5a2ee888f11a8490ce1a7acdfa8f4b95154e477add075687 |
| c01 | A5 | deterministic_gates, gate_a | c3ade5af91a69a12cb496b8fc1676332fcadbd4b1c81e7178198864a3b480416 |
| c01 | dual | deterministic_gates, gate_a | 254099d0743422867b7bcf377d4c5e8be52c9d5612aa2ef342345fe0013d3f56 |
| c02 | A0 | deterministic_gates | d5b4329548b18059d6b21c95074c5dd3c31fdf05878b0112423df5e0bec673da |
| c02 | A1 | deterministic_gates | 451a8e7a4dc549a95bd3024ff43cedf05972c58102200c4912f33e46c7f9d7db |
| c02 | A2 | deterministic_gates | 6d27ecb648092aa34a60cb36f10e2633769d0046b37e70d8d61c8679d7c5b6ee |
| c02 | A3 | deterministic_gates | 6f1aeb507965227dea564f8d53d1d894718bbfe6ab26f5bbb65b482e0ea7bdb2 |
| c02 | A4 | deterministic_gates | ff861f5d90c3307b17968269e302dbd62a620248bd83b3f187bee6a9ffbe46cd |
| c02 | A5 | deterministic_gates | 393f60abf4d2f2a448e23fcb66f45841b7082ca4a1c0aeefe021e9be6bb17d10 |
| c02 | dual | deterministic_gates | 9644e25859020e16f7f703220acb2e7e6af5aecacc6e5445be338f81d3acd1fb |
| c03 | A0 | deterministic_gates, human_review | 7d3a236b41fbf3b8db68f007f60729903f9d7e7778c6e284ae92e1dbb5e56aaf |
| c03 | A1 | deterministic_gates, sol_review | 422598407d9a540234c2afccbff9baaea1c72c9ee1b1fd795e7e1de55f56dd72 |
| c03 | A2 | deterministic_gates, gate_a, human_review | 7fa0c0f6b24aea017f3dd7eb06e23dc11d90b74169ea1716e650b774dc8d1ab2 |
| c03 | A3 | deterministic_gates, sol_review, gate_b | b5cf7be599d0bfbb2da7c108182b60b816b98a6f0ab931b0ad1462ed95bdb883 |
| c03 | A4 | deterministic_gates, gate_a | 16d4fe46295dbe3d8c4a9137898430bdb01503d4ff933547da7da1769d0a5b6e |
| c03 | A5 | deterministic_gates, gate_a | addf286cf75a65a94bd57773fe5eea95319a65c5b750f7668f1c78a49f5e677e |
| c03 | dual | deterministic_gates, gate_a | afb2098c065b2e03ede073c5b41a0e22fc9774702cbd777dfc2289110b877caf |
| c04 | A0 | deterministic_gates, human_review | 3caa385881c117365459606acd56273508e53bfdd842ac237056a28b2ecb63cf |
| c04 | A1 | deterministic_gates, sol_review | 54866cea50cf7825690cbedefcc5e2e1887e3f58bce79443fabfcd669ae2b166 |
| c04 | A2 | deterministic_gates, gate_a, sol_review, human_review | b2bb97244e39985413ed8ca102bc5f01b32e6165216411bd2dea89b85830a803 |
| c04 | A3 | deterministic_gates, sol_review, gate_b | 4a1213152b2e56a7e186e29046b077b7c766b36eb6a56dd3fac71fbe671c1a8f |
| c04 | A4 | deterministic_gates, gate_a, sol_review, gate_b | ba4880ca5774001ad11560d3bdd8c1cad4e3d50be04cc9f8e205b3f5cb1fe5c6 |
| c04 | A5 | deterministic_gates, gate_a, sol_review, gate_b | 1c2b31370535d90f7b79051078ea0e4f98feb456f8ed8cbc54f62f11f650b67e |
| c04 | dual | deterministic_gates, gate_a, sol_review, dual_review, gate_b | bd2200a6ac5d706990d21396fb5e5b243940ee769404969ab4a94904bac136bb |
| c05 | A0 | deterministic_gates, human_review | da320dc02a68cbdb3d1cfac493a90aee54786543510813f5c9e976c208a1d7f5 |
| c05 | A1 | deterministic_gates, sol_review | 80d412d2bf773ba2d74845257cb8ff0c4d311a5784462b88e1db3e5fe199cc83 |
| c05 | A2 | deterministic_gates, gate_a, sol_review, human_review | 1b6a621a5f64a7098f74096af73c1d195e4b6f776905d4126eabd0b7768d8ee0 |
| c05 | A3 | deterministic_gates, sol_review, gate_b | a5a1e009847f8f9cc26ae13e4aefd2fd74a4b232ba2955366cde59506cca8d44 |
| c05 | A4 | deterministic_gates, gate_a, sol_review, gate_b | a2504452cebf0cc5a5c203ec0618fed59a59491da14047027432d9dce4b8a47d |
| c05 | A5 | deterministic_gates, gate_a, sol_review, gate_b | 9cb4b09ca0fdcf270bc7e80e83414e04681d1f2ac49ee29d802284846adcacf1 |
| c05 | dual | deterministic_gates, gate_a, sol_review, gate_b | 012b8641589a9d8dbc9277bb1739846b00feef0cb9d83c4ca2e3db26df836780 |
| c06a | A0 | deterministic_gates, human_review | 7ff8c6b22f4e4e809b16f9ed8e6cec5b1f9989ce436733393f2b0f897fb110d3 |
| c06a | A1 | deterministic_gates, sol_review | 16cde930631a25d0ad97cd68f4b3fe762fe08fc0ecbaf174ad10a70fa448965a |
| c06a | A2 | deterministic_gates, gate_a, sol_review, human_review | 93badcda3d742b798177d200d05e0858faa3d4c7456d515dc55a28b89ddc81b8 |
| c06a | A3 | deterministic_gates, sol_review, gate_b, remediation_loop | 8154ce752860a36281cfffbbc030c539e07945141d7f1e653fe1daf0fe992bb1 |
| c06a | A4 | deterministic_gates, gate_a, sol_review, gate_b, remediation_loop | 00ba0875227a4b8d45a7fc998e4eb1f289b3bb4e209ed54a192dd5c8f36e8056 |
| c06a | A5 | deterministic_gates, gate_a, sol_review, gate_b, remediation_loop | c4d95070d4f5b0ceef811210229a51e348573ab3dee8fcd020b58aac64c4dd68 |
| c06a | dual | deterministic_gates, gate_a, sol_review, gate_b, remediation_loop | 95f6b3df37938e2002bffc047573bd2d1699d486c4127aff44f930b1e1a47e24 |
| c06b | A0 | deterministic_gates, human_review | 39422fd8ef73d9c38af8d3a57760e7a1ed77aacfdf06e66c9b1e20beec9be47f |
| c06b | A1 | deterministic_gates, sol_review | 25d6fc7ccd77a7543c32c70362a9b42e99398d2751276c3b72aa5977b831500c |
| c06b | A2 | deterministic_gates, gate_a, human_review | 3d8798fb7f48f1552ea1ac5723a495413b742727cd7a8a6d0145e57b932fd2b3 |
| c06b | A3 | deterministic_gates, sol_review, gate_b | d657deef40354acccc3fdebfa360b9f6e4211cc35c4c099a3513756979df64af |
| c06b | A4 | deterministic_gates, gate_a | e028494e8719c7b64dec54ef6a2dbd74aaedfc8f75712fb64f536cfdc57b7331 |
| c06b | A5 | deterministic_gates, gate_a | fa3d211e1553011c5bb6523826cad0dbe3e7ce1253392dedd01fd5324640b1d2 |
| c06b | dual | deterministic_gates, gate_a | d59a71bfa85a39a44ff65272211ee622b3c177c9937d8e7aa83e395142b1adf3 |
| c07 | A0 | deterministic_gates, human_review | 9540252de24cbf0f14da290022a003e105b46be86f737249f72cf8dbf2a2ab05 |
| c07 | A1 | deterministic_gates, sol_review, human_review | a6bf7422d2221904ce728ca429bfdb9bc8e647a1604be37336c985ff6e85cc62 |
| c07 | A2 | deterministic_gates, gate_a, sol_review, human_review | 6a9202a162602ba5868b3bc263bbcb32a136391d377a9dcdc99774826995cce5 |
| c07 | A3 | deterministic_gates, sol_review, gate_b, human_review | 4b17769dc2446d824bb3d0979ba042aaaf147dbe69f52a09bdf3c048522f1985 |
| c07 | A4 | deterministic_gates, gate_a, sol_review, gate_b, human_review | 8aef49d35db73837316dffbe0250c8b46062edae32fe40eb1a73db0360c83064 |
| c07 | A5 | deterministic_gates, gate_a, sol_review, gate_b, human_review | 6f2aa00fbe804ec0d1f11887639a036fb614b28c30b56d9a880fd202f553dbab |
| c07 | dual | deterministic_gates, gate_a, sol_review, dual_review, gate_b, human_review | 8a830db2536d57d628b076ba157ce76bb3a17025bd4fa5b999ff107027f6f615 |
| c08 | A0 | deterministic_gates, human_review | 8f9ae68f8170eadb27630ddd4cc5a278fdc09d5e05fc5370f8a0fc33421aadd6 |
| c08 | A1 | deterministic_gates, sol_review | 8cd776f5fa34ffa38a8f963a84475cd3c72551e55fed8c3d7105f46bba12f8c2 |
| c08 | A2 | deterministic_gates, gate_a, human_review | 0a4787513c9a230a11ebaa7e97d660f60c805325ca9ef945fffbfd5c84a53b58 |
| c08 | A3 | deterministic_gates, sol_review, gate_b | 9e371d14cbb3ed98ea5ca486b32a8566286508ee1ccd56cc76213317fdf9e55b |
| c08 | A4 | deterministic_gates, gate_a | e9858f882c98fd18562311c40f5bf7861de46102dee2fb8c8feb425c25c2135a |
| c08 | A5 | deterministic_gates, gate_a | 4e32f8a9a757048c3f6ea3124b9702e3df82e33ac08a9817ee77a99e7820ace5 |
| c08 | dual | deterministic_gates, gate_a | 1ec53d735f4b9cb8de1b3b2ffda15a3b231377da6aa4c036428c449d859d947c |
| c09 | A0 | deterministic_gates, human_review | 32638620cd9256a0ac1ea0667904be187757d98c3fccad67d057d4dbefdf6ecc |
| c09 | A1 | deterministic_gates, sol_review | 08887d146902077fd0f484b8ca3936a5592e4981bd18dd01f501625d56d95a6b |
| c09 | A2 | deterministic_gates, gate_a, sol_review, human_review | 58b6d8ea0a9690a2be776d19933772c5031a0ef25813e4ebf31beb1d495413ae |
| c09 | A3 | deterministic_gates, sol_review, gate_b | 055aad661a4cbb886deeb7f4182a5f28ad0a08ad906b1891a0b15cc6f38da7c6 |
| c09 | A4 | deterministic_gates, gate_a, sol_review, gate_b | 392aaca7aede5a00d7fd0fbbb404339319f73a5101f04008fbb59eb38822e873 |
| c09 | A5 | deterministic_gates, gate_a, sol_review, gate_b | 3452af43b5bcc9ac30c8921860589c5604feb06b0edf8e060fecd025f89a449f |
| c09 | dual | deterministic_gates, gate_a, sol_review, dual_review, gate_b | 32095e06b4b34ec0b4acf32cd68bccf15b10d782a2580c646dc18be5267bb94a |

## Metric-registry coverage

**Table (backend=mock; source=simulated; n=37; simulated).**
| metric | population | numerator | denominator | numerator_value | denominator_value | source | value | unavailable_reason |
|---|---|---|---|---|---|---|---|---|
| blocker_recall | expected_blockers | matched_blockers | expected_blockers | None | None | score | None | None |
| blocker_recall_simulated | expected_blockers | matched_blockers | expected_blockers | None | None | score | 1.0 | None |
| cost_per_blocker | matched_blockers | total_cost | matched_blockers | None | None | costing | None | no_available_usage |
| cost_per_material_finding | matched_material_findings | total_cost | matched_material_findings | None | None | costing | None | no_available_usage |
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
| material_recall_including_blocker_simulated | expected_material_and_blocker | matched_material_and_blocker | expected_material_and_blocker | None | None | score | 1.0 | None |
| material_recall_only | expected_material | matched_material | expected_material | None | None | score | None | None |
| material_recall_only_simulated | expected_material | matched_material | expected_material | None | None | score | 1.0 | None |
| overcall_rate | produced_findings | unmatched_findings | produced_findings | None | None | score | None | None |
| overcall_rate_simulated | produced_findings | unmatched_findings | produced_findings | None | None | score | 0.0 | None |
| remediation_eligibility_rate | review_cases | simulated_remediation_routes | review_cases | 17 | 63 | run | 0.2698412698412698 | None |
| required_but_unmentioned | required_requirements | uncited_requirements | required_requirements | None | None | score | None | None |
| required_but_unmentioned_simulated | required_requirements | uncited_requirements | required_requirements | None | None | score | 6 | None |
| requirement_coverage_recall | cited_expected_requirements | independently_covered | cited_expected_requirements | None | None | score | None | None |
| requirement_coverage_recall_simulated | cited_expected_requirements | independently_covered | cited_expected_requirements | None | None | score | 1.0 | None |
| review_loops | linked_fixed_head_rows | real_re_review_artifacts | linked_fixed_head_rows | 0 | 7 | artifact | 0.0 | None |
| review_loops_simulated | linked_fixed_head_rows | simulated_re_review_artifacts | linked_fixed_head_rows | 4 | 7 | artifact | 0.5714285714285714 | None |
| severity_exactness_rate | matched_findings | exact_severity_matches | matched_findings | None | None | score | None | None |
| severity_exactness_rate_simulated | matched_findings | exact_severity_matches | matched_findings | None | None | score | 1.0 | None |
| sol_avoidance_rate | eligible_cases | cases_without_sol | eligible_cases | 25 | 63 | run | 0.3968253968253968 | None |
| sol_calls_per_pr | cases | sol_calls | cases | 41 | 70 | run | 0.5857142857142857 | None |
| spurious_blocker_rate | produced_findings | unmatched_blockers | produced_findings | None | None | score | None | None |
| spurious_blocker_rate_simulated | produced_findings | unmatched_blockers | produced_findings | None | None | score | 0.0 | None |
| throughput | completed_cases | cases | elapsed_wall_time | None | None | observation | None | None |
| tokens | measured_cases | input_plus_output_tokens | measured_cases | None | None | usage | None | no_available_usage |
| tokens_simulated | simulated_cases | input_plus_output_tokens | simulated_cases | None | None | usage | None | no_available_usage |

## No-claims section

- Mock values are simulated mechanics drivers, not measured model outcomes.
- This report makes no model-quality or calibration-quality claim.
- Costs are not real savings and remediation is not autonomous.
- A5 and dual reviewer lanes are wiring simulations, not independence claims.

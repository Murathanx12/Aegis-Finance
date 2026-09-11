# Research notes: NN for cross-sectional return prediction

## Section 1: Patents
- US10452978B2 "Attention-based sequence transduction neural networks" (Shazeer et al, Google) - the transformer patent. patents.google.com/patent/US10452978B2/en
- Google Open Patent Non-Assertion (OPN) Pledge exists but transformer/deep-learning patents NOT on the OPN list per piip.co.kr source
- Apache 2.0 (TensorFlow, JAX, PyTorch-adjacent via HF Transformers, T5) includes patent grant clause: any contributor's patents reading on their contribution are licensed to users; if you sue over patent infringement re that software, your license terminates (defensive termination)
- OIN: 4100+ members cross-license patents against each other for Linux-ecosystem/open source use; core to Android/Linux stack, less clearly ML-specific
- PyTorch: BSD-3 license (not Apache) - no explicit patent grant clause in BSD-3-Clause itself, but Meta/Linux Foundation govern IP separately

## Section 2/3 architectures
- DLinear/"Are Transformers Effective" (Zeng et al, AAAI 2023) beat transformers on LTSF; PatchTST (ICLR 2023) beat DLinear via patching; iTransformer (ICLR 2024) inverts attention over variates
- MASTER AAAI2024 github.com/SJTU-DMTai/MASTER - market-guided cross-stock attention
- StockMixer AAAI2024 github.com/SJTU-DMTai/StockMixer - MLP mixer, cheap, strong, good 8GB fit
- StockFormer IJCAI2023 - predictive coding + RL hybrid
- HAN/Hu et al 2018 WSDM "Listening to Chaotic Whispers"; Hierarchical Complementary Attention Network (CIKM 2018)
- Ding et al 2015 IJCAI event-driven (event embeddings + CNN), 2016 knowledge-graph NTN extension
- Chen Kelly Xiu "Expected Returns and LLMs" SSRN 4416687, orig 2022 updated through 2026
- Lopez-Lira & Tang arXiv:2304.07619 "Can ChatGPT Forecast Stock Price Movements?" v6 Oct 2025; note Sarkar&Vafa 2024 + Lopez-Lira/Tang/Zhu 2025 flag look-ahead/memorization risk pre-cutoff
- Chronos/TimesFM/Moirai foundation models - zero-shot decent on general TS, not finance-specific validated

## Section 4 self-learning
- ADWIN adaptive windowing drift detector, used w/ ensembles in financial concept-drift literature
- Conformal Predictive Portfolio Selection (Kato et al, arXiv 2410.16333) - CP for portfolio return intervals
- Conformal coverage degrades in high-vol regimes for daily stock returns (~90%->50%) per search summary
- Adaptive Conformal Inference / nonexchangeable CP for non-stationary financial series

## Section 5 tokenization
- NumBERT/NumGPT: scientific notation encoding of numbers; GenBERT: digit-by-digit
- Consensus: digit-level tokenization / place-value embeddings needed for arithmetic; BPE bad for numbers
- Practical answer: don't build a number tokenizer - convert financial numbers to relative-to-expectation features (surprise vs consensus) and feed as separate numeric channel, use pretrained text tokenizer/encoder as-is for prose

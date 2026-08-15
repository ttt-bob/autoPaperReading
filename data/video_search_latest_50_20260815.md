# 最新 50 篇视频检索论文增量综述（2026-08-15）

本报告是 `video_search_model_dataset_summary.md` 的增量论文清单。50 篇论文均已下载 PDF、
基于正文生成中文结构化总结并写入本地数据库，同时导出到网页详情 JSON。论文发布时间覆盖
2026-03-12 至 2026-08-13，按 arXiv 当前可检索到的最新版本去重。

## 核心趋势

1. **检索对象从短 clip 转向小时、天、月级视频记忆。** 新工作不再只做全局相似度，
   而是显式构建层次索引、对象记忆、时序缓存或可组合 KV memory。
2. **长视频理解与问答成为最大增量。** 两类合计 27 篇，重点从“塞入更多帧”转向查询感知
   压缩、显式记忆、跨视频索引和证据检索；时刻检索与视频接地另有 16 篇，持续强化精确定位。
3. **“先检索、再验证”正在替代一次性回答。** 多篇工作采用 propose-verify、
   plan-verify、backtracking 或 evidence graph，把可追溯时间段作为答案依据。
4. **查询感知压缩是长视频落地的关键。** 帧选择、clip trimming、token folding、
   event-centric sampling 等方法试图只保留与查询有关的少量视觉证据。
5. **评测开始关注模型到底用了什么证据。** 新基准加入因果链、跨视频推理、细粒度活动、
   月级第一视角记忆与时空证据校验，避免只用最终答案准确率掩盖捷径。
6. **通用检索仍需要专门的 embedding 与重排。** Video-LLM embedding、组合视频检索、
   长尾短视频重排与细粒度关系学习说明，大模型推理层不能替代高吞吐召回层。

## 方向分布

| 方向 | 数量 | 工程位置 |
| --- | ---: | --- |
| 长视频理解 | 14 | 长视频压缩、记忆和查询规划 |
| 视频问答 | 13 | 结果解释、问答与证据验证 |
| 视频接地 | 10 | 时间/空间证据定位 |
| 视频时刻检索 | 6 | 候选片段精定位与多片段召回 |
| 视频检索 | 5 | 向量召回、组合检索与重排 |
| 时序动作定位 | 1 | 开放词表动作时间定位 |
| 视频异常检测 | 1 | 工业/安防异常检测与定位 |

## 50 篇逐篇一句话总结

### 视频时刻检索（6 篇）

- **[Conditional Multi-Event Temporal Grounding in Long-Form Video](http://arxiv.org/abs/2606.15320v1)**（2026-06-13，2606.15320v1）：本文提出CoMET-Bench——首个面向长视频的条件多事件时间定位基准（含2,789个查询、600个视频），并配套统一评估协议和Rejection-F1指标，同时提出训练免费的CoMET-Agent智能体框架，通过结构化搜索-聚合将F1@0.5提升6.1%。
- **[Natural-Language Temporal Grounding in Hour-Long Videos is a Search Problem: A Benchmark and Empirical Decomposition](http://arxiv.org/abs/2606.12300v1)**（2026-06-10，2606.12300v1）：本文发布首个开放的小时级自然语言时间定位基准ExtremeWhenBench（2,273个查询/194个视频，平均75.7分钟），并通过实证分解证明小时级时间定位的瓶颈是搜索而非识别——所有开放Video-LLM在小时级视频上性能崩塌，而帧级检索基线反而超越它们，85%的失败归因于搜索失败，retrieve-then-ground混合方法比单体Video-LLM提升6.7倍。
- **[GIRL-DETR: Gradient-Isolated Reinforcement Learning for Video Moment Retrieval](http://arxiv.org/abs/2606.00775v1)**（2026-05-30，2606.00775v1）：GIRL-DETR首次将强化学习后训练引入轻量级视频时刻检索模型，通过梯度隔离策略冻结骨干网络、仅更新检测头，并采用三阶段渐进式RL策略直接优化非可微的tIoU指标，有效解决了代理损失退化问题。
- **[Not All Inputs Are Valid: Towards Open-Set Video Moment Retrieval Using Language](http://arxiv.org/abs/2605.29812v1)**（2026-05-28，2605.29812v1）：本文首次提出开放集视频时刻检索（OS-VMR）任务，并设计了一个名为OpenVMR的框架，利用归一化流技术学习ID查询分布、推理ID-OOD分离边界，并基于ID查询进行跨模态交互和时刻检索，实现对OOD查询的拒绝和ID查询的准确检索。
- **[Fewer Steps, Better Performance: Efficient Cross-Modal Clip Trimming for Video Moment Retrieval Using Language](http://arxiv.org/abs/2605.29793v1)**（2026-05-28，2605.29793v1）：本文提出SpotVMR，一种基于查询条件化的高效视频片段选择方法，通过轻量级BAM语义索引特征和递归片段选择机制，仅对少量查询相关片段进行昂贵的跨模态交互，在显著提升推理效率的同时保持甚至提升VMR检索性能。
- **[Multi-proposal Collaboration and Multi-task Training for Weakly-supervised Video Moment Retrieval](http://arxiv.org/abs/2605.14838v1)**（2026-05-14，2605.14838v1）：本文提出了一种名为MCMT（Multi-proposal Collaboration and Multi-task Training）的弱监督视频时刻检索方法，通过多高斯掩码提案协作生成高质量正样本掩码，并引入前向与逆向双掩码查询重建任务来增强模型训练的约束力和稳定性。

### 长视频理解（14 篇）

- **[EgoCITE: Context-Augmented Indexing and Time-Aware Retrieval for Long-Horizon Egocentric Memory](http://arxiv.org/abs/2608.12627v1)**（2026-08-12，2608.12627v1）：EgoCITE提出了一种面向长时程第一视角问答的智能体记忆框架，通过上下文增强的原子记忆索引（EgoScheme）和多视图时间感知检索（EgoIndex与EgoRetrv），显著优于现有智能体记忆基线，同时比长上下文LLM智能体降低36倍成本。
- **[StreamFlow: Dynamic Memory Flows for Streaming Video Understanding](http://arxiv.org/abs/2608.10949v1)**（2026-08-11，2608.10949v1）：StreamFlow 提出了一种高效、冻结骨干的视觉记忆框架，通过“动态感知中期记忆 + 潜在长期记忆 + 注意力引导注入”实现对历史视觉信息的按需访问，在流式视频理解上取得当前最优性能，同时显著提升视觉接地性和推理效率。
- **[ChronoStitch: Training-Free Composition of Visual KV Memories for Long-Horizon Temporal Reasoning](http://arxiv.org/abs/2607.19547v1)**（2026-07-21，2607.19547v1）：ChronoStitch提出一种免训练的两阶段视觉KV记忆合成方法：先通过三轴mRoPE增量旋转将独立存储的键重定位到全局时间-高度-宽度坐标系，再选择性重计算后续分块中偏差最大的少量视觉token以恢复缺失的跨块注意力，从而在不重新处理整个视频的前提下实现长时程时间推理。
- **[BLUE: Semantics-Preserving Video Compression for Efficient Vision-Language Surveillance Analytics](http://arxiv.org/abs/2607.19515v1)**（2026-07-21，2607.19515v1）：论文提出并评估了一种面向固定摄像头监控视频的机器中心压缩方法 BLUE，它通过持久背景建模和前景保留，在保持 VLM 语义推理质量几乎不变的前提下，降低文件大小并利用跳帧型 P 帧信号减少 VLM 调用次数。
- **[HPP: Hierarchical Programmatic Probing for Long Video Understanding by Decoupling Perception and Reasoning](http://arxiv.org/abs/2606.21734v1)**（2026-06-19，2606.21734v1）：本文提出HPP框架，通过将长视频理解重构为对分层分割视频的迭代程序化探测，将语义感知与高阶时序推理解耦，使具备编码能力的LLM在交互式编码环境中规划并执行多步策略，按需调用轻量级VLM进行局部感知，从而显著提升长视频理解性能。
- **[Temporal Backtracking Search for Test-time Generative Video Reasoning](http://arxiv.org/abs/2606.13861v1)**（2026-06-11，2606.13861v1）：本文提出时间回溯搜索（Temporal Backtracking Search, TBS），将视频生成的测试时搜索空间从去噪轴转移到时间轴，通过生成-验证-重启的迭代循环，利用已验证的前缀锚点进行分支修复，从而显著提升视频模型的长时程推理能力。
- **[Q-Fold: Query-Aware Focus-Context Spatio-Temporal Folding for Long Video Understanding](http://arxiv.org/abs/2606.12125v1)**（2026-06-10，2606.12125v1）：Q-Fold提出了一种无需训练的查询感知焦点-上下文时空折叠框架，通过将连续时间片段组织为异构的焦点-上下文表示，在固定视觉预算下同时保留关键视觉证据和广泛时序覆盖，显著提升长视频理解性能。
- **[Linear Scaling Video VLMs for Long Video Understanding](http://arxiv.org/abs/2605.31598v1)**（2026-05-29，2605.31598v1）：本文提出StateKV，一种无需微调或架构修改的推理时方法，通过固定容量、基于重要性的循环状态携带跨帧上下文，并配合完整的逐帧缓存用于解码，将预训练长视频VLM的视频预填充复杂度从二次方降至线性，在多个基准和模型上接近全自注意力性能并优于滑动窗口方法。
- **[Semantic and Visual Evidence for Efficient Long-Video Reasoning: A Solution for the HD-EPIC VQA Challenge](http://arxiv.org/abs/2605.29402v1)**（2026-05-28，2605.29402v1）：本文提出一个两阶段证据引导框架，通过离线构建可复用的语义证据（结构化文本）和视觉证据（对象级边界框与视觉嵌入），并在在线推理时进行查询条件化的证据检索与整合，从而高效解决长时程第一视角视频问答问题，在HD-EPIC VQA挑战中取得65.8%的整体准确率，显著超越所有基线方法。
- **[CREST: Curvature-Regulated Event-Centric Sampling for Efficient Long-Video Understanding](http://arxiv.org/abs/2605.09223v3)**（2026-05-09，2605.09223v3）：CREST提出了一种基于查询-帧相关性时间信号局部曲率的无训练帧选择方法，通过曲率调节的非极大值抑制在固定帧预算下更有效地分配帧资源，在保持接近MIRA准确率的同时将预处理成本降低至其3-4%。
- **[SYNCR: A Cross-Video Reasoning Benchmark with Synthetic Grounding](http://arxiv.org/abs/2605.08412v1)**（2026-05-08，2605.08412v1）：SYNCR是一个基于合成仿真引擎（Habitat、Kubric和CLEVRER）构建的跨视频推理基准，通过程序化验证的精确真值，系统评估MLLMs在时间对齐、空间追踪、比较推理和整体综合四个诊断维度上的能力，揭示了当前模型与人类表现之间的显著差距。
- **[Where to Focus: Query-Modulated Multimodal Keyframe Selection for Long Video Understanding](http://arxiv.org/abs/2604.17422v1)**（2026-04-19，2604.17422v1）：Q-Gate提出了一种无需训练、即插即用的查询调制门控框架，将关键帧选择建模为动态模态路由问题，通过LLM分析查询意图并动态分配三个互补专家流（视觉定位、全局匹配、上下文对齐）的注意力权重，从而在长视频理解中最大化信噪比并显著超越现有基线。
- **[One Token per Highly Selective Frame: Towards Extreme Compression for Long Video Understanding](http://arxiv.org/abs/2604.14149v2)**（2026-04-15，2604.14149v2）：本文提出XComp框架，通过可学习渐进式token级压缩（LP-Comp）和问题条件帧级压缩（QC-Comp）实现每帧仅保留一个token的极端压缩，使VLM能够处理2-4倍更多的视频帧并提升长视频理解性能。
- **[Mosaic: Cross-Modal Clustering for Efficient Video Understanding](http://arxiv.org/abs/2604.10060v1)**（2026-04-11，2604.10060v1）：Mosaic是首个基于跨模态聚类的VLM推理系统，通过将KVCache组织、维护和检索的基本单元从token级提升到跨模态簇级，实现了流式长视频理解的高效推理，最高可获得1.38倍加速和2.22倍GPU内存节省。

### 视频问答（13 篇）

- **[EgoMonth: A Month-Level Egocentric Video Benchmark for Long-Term Spatiotemporal Memory](http://arxiv.org/abs/2608.13113v1)**（2026-08-13，2608.13113v1）：EgoMonth 是首个月级别的第一视角视频理解基准，包含 300+ 小时真实日常生活录像和 1,443 个多选问答对，通过 14 个任务的三层认知框架揭示了当前 MLLMs 在长期时空记忆上远逊于人类，本质上是“有损摘要器”而非“忠实记忆器”。
- **[R4DSG: Relative 4D Scene Graph Memory for Object-Centric Question Answering in Long Egocentric Video](http://arxiv.org/abs/2608.11017v1)**（2026-08-11，2608.11017v1）：R4DSG提出了一种基于"相对4D场景图记忆"的方法，将长期自我中心RGB视频转换为以静态锚点和动态物体为核心的可查询记忆条目，从而在不依赖全局坐标系或强几何输入的前提下支持物体中心的长期问答。
- **[GHR-VLM: Making Zero-Shot Transit Video Analytics Realizable with Grounded Hybrid Reasoning](http://arxiv.org/abs/2607.13569v2)**（2026-07-15，2607.13569v2）：GHR-VLM提出了一种视觉接地混合推理框架，通过边缘-云端协作架构，将轻量级边缘感知模块（门状态检测、乘客跟踪）与后端VLM的开放词汇语义推理相结合，实现零样本的公交视频乘客支付行为分析。
- **[What Does a Temporal Benchmark Score Measure? Decomposing Channel Use in Video VLM Evaluation](http://arxiv.org/abs/2607.12304v1)**（2026-07-14，2607.12304v1）：本文提出了一种无需标注的"反转下降"（reversal-drop）筛查方法，通过将视觉帧序列反转而保持RoPE位置编码正向，来分解视频VLM在时间基准测试中使用的信息通道，揭示模型是位置主导型还是视觉序列主导型。
- **[ReQuest: Rethinking-based Question-Aware Frame Selection for Long-Form Video QA](http://arxiv.org/abs/2607.01737v1)**（2026-07-02，2607.01737v1）：ReQuest提出了一种基于不确定性驱动的、问题自适应的关键帧选择框架，通过轻量级选择器、重思考路由和自适应NMS采样策略，在不修改或微调底层MLLM的情况下提升长视频问答的准确性。
- **[ViTexQA: A Multi-Frame Temporal Perception Dataset for Video Text Question Answering](http://arxiv.org/abs/2606.24602v1)**（2026-06-23，2606.24602v1）：本文提出了ViTexQA——首个专门针对多帧时间感知的视频文本问答数据集（所有问题均无法从单帧回答），并配套提出了FrameThinker训练方法，通过CoT引导的监督微调和时间接地强化学习两阶段训练，显著提升了MLLMs的跨帧文本推理能力。
- **[TimeProVe: Propose, then Verify for Efficient Long Video Temporal Reasoning in Activities of Daily Living](http://arxiv.org/abs/2606.20561v1)**（2026-06-18，2606.20561v1）：TimeProVe提出了一种成本高效的混合框架，先用轻量级模块生成基于动作的答案-证据假设，再仅对选定的短视频片段调用昂贵的VLM进行定向验证，从而在保持高准确率的同时大幅降低长视频问答的计算成本。
- **[SuperMemory-VQA: An Egocentric Visual Question-Answering Benchmark for Long-Horizon Memory](http://arxiv.org/abs/2606.00825v1)**（2026-05-30，2606.00825v1）：本文提出了SuperMemory-VQA，一个包含52.9小时多模态自我中心视频和4,853个经过人工验证的问答对的长时记忆VQA基准数据集，用于评估AI助手在真实、长期记忆任务上的表现，并揭示了现有系统在可回答性检测、长时间间隔推理和多证据整合方面的重大不足。
- **[CaST-Bench: Benchmarking Causal Chain-Grounded Spatio-Temporal Reasoning for Video Question Answering](http://arxiv.org/abs/2605.23216v2)**（2026-05-22，2605.23216v2）：CaST-Bench是一个全新的视频问答基准，通过提供带时间戳和边界框轨迹的链式时空因果证据，首次实现了对视觉语言模型因果链接地时空推理能力的严格评估。
- **[FineBench: Benchmarking and Enhancing Vision-Language Models for Fine-grained Human Activity Understanding](http://arxiv.org/abs/2605.19846v3)**（2026-05-19，2605.19846v3）：本文提出了FineBench——一个包含199,420个QA对、基于64个长视频的密集标注人类中心视频问答基准，并提出了FineAgent模块化框架，通过Localizer和Descriptor组件显著提升开放源码VLMs在细粒度人类活动理解上的表现。
- **[Minerva-Ego: Spatiotemporal Hints for Egocentric Video Understanding](http://arxiv.org/abs/2605.15342v1)**（2026-05-14，2605.15342v1）：本文提出Minerva-Ego，一个基于HD-EPIC的长时程egocentric视频推理基准，为每个问题提供密集的时空推理轨迹注释，并通过实验证明利用"何时何地看"的时空提示可显著提升前沿模型的推理准确率。
- **[UpstreamQA: A Modular Framework for Explicit Reasoning on Video Question Answering Tasks](http://arxiv.org/abs/2604.23145v1)**（2026-04-25，2604.23145v1）：UpstreamQA提出一个模块化两阶段框架，通过多模态大型推理模型（LRMs）执行对象识别和场景上下文生成等上游推理任务，再将推理结果传递给下游LMMs进行VideoQA，系统评估显式推理对视频问答性能和可解释性的影响。
- **[VideoZeroBench: Probing the Limits of Video MLLMs with Spatio-Temporal Evidence Verification](http://arxiv.org/abs/2604.01569v1)**（2026-04-02，2604.01569v1）：VideoZeroBench是一个面向长视频理解的分层基准，通过五级评估协议严格验证模型的时空证据定位能力，揭示当前视频MLLMs在标准QA下准确率不足17%、在严格时空定位要求下准确率低于1%的严重能力瓶颈。

### 视频接地（10 篇）

- **[Plan-and-Verify Video Reward Reasoning with Spatio-Temporal Scene Graph Grounding](http://arxiv.org/abs/2606.11838v1)**（2026-06-10，2606.11838v1）：SG-PVR提出了一种基于时空场景图（Spatio-Temporal Scene Graph）的"规划-验证"（Plan-and-Verify）视频奖励推理框架，通过将提示词分解为原子验证声明并逐一对照视频和场景图进行验证，实现了细粒度的语义对齐评估。
- **[Temporal-Aware Reasoning Optimization for Video Temporal Grounding](http://arxiv.org/abs/2606.09248v1)**（2026-06-08，2606.09248v1）：本文提出TaRO（Temporal-Aware Reasoning Optimization）框架，通过构建性推理探索和时序敏感性奖励，显式增强MLLMs在视频时间定位中"随时间思考"的能力，实现最先进的性能。
- **[Rethinking Weakly-supervised Video Temporal Grounding From a Game Perspective](http://arxiv.org/abs/2605.26441v1)**（2026-05-26，2605.26441v1）：本文首次从博弈论视角重新审视弱监督视频时间定位任务，将视频帧和查询词建模为博弈玩家，通过多元合作博弈理论学习帧-词间细粒度的不确定跨模态对应关系，从而无需时刻提案即可实现精确的时刻定位。
- **[EVIDENT: Routing MLLM Adaptation through Entity-Grounded Visual Evidence for Cross-Domain Video Temporal Grounding](http://arxiv.org/abs/2605.26104v1)**（2026-05-25，2605.26104v1）：本文提出EVIDENT框架，通过实体瓶颈适配器、实体绑定蒸馏和实体到证据门控机制，将VTG微调锚定在预训练MLLM固有的实体注意力能力上，以实体级视觉证据驱动时间定位，从而显著提升跨域鲁棒性。
- **[Foresee-to-Ground: From Predictive Temporal Perception to Evidence-Driven Reasoning for Video Temporal Grounding](http://arxiv.org/abs/2605.21973v1)**（2026-05-21，2605.21973v1）：F2G将视频时间定位重构为可验证的"先识别后测量"（Identify-then-Measure）问题，通过预测性时间感知构建候选事件段证据池，并让LLM基于可引用的证据单元进行边界预测，从而将黑盒时间戳回归转变为结构化、可归因的推理过程。
- **[MLLMs Know When Before Speaking: Revealing and Recovering Temporal Grounding via Attention Cues](http://arxiv.org/abs/2605.21954v1)**（2026-05-21，2605.21954v1）：本文通过注意力头敲除实验发现MLLMs中存在稀疏的"时间定位头"（TG-Heads），揭示了模型在预填充阶段已知道正确时间区间但在解码阶段丢失该信号的"感知-生成鸿沟"，并提出一个无需参数更新的推理时"读取-再生成"框架来恢复这一隐藏信号，从而提升视频时间定位精度。
- **[Static and Dynamic Graph Alignment Network for Temporal Video Grounding](http://arxiv.org/abs/2605.00684v1)**（2026-05-01，2605.00684v1）：本文提出静态与动态图对齐网络（SDGAN），通过联合建模静态和动态视觉特征、引入查询-片段对比学习与自适应图建模，以及采用渐进式易到难训练策略，有效解决了时序视频定位中视觉表示不完整、查询无关图构建和单一粒度训练三大问题。
- **[UniversalVTG: A Universal and Lightweight Foundation Model for Video Temporal Grounding](http://arxiv.org/abs/2604.08522v1)**（2026-04-09，2604.08522v1）：UniversalVTG通过引入离线查询统一器（Query Unifier）将异构查询格式规范化到共享语义空间，结合高效视觉骨干和轻量级定位头，在超过100万查询-片段对上大规模跨数据集预训练，实现了一个比MLLM方法小两个数量级但性能相当或更优的通用轻量级视频时间定位基础模型。
- **[Bridging Time and Space: Decoupled Spatio-Temporal Alignment for Video Grounding](http://arxiv.org/abs/2604.08014v3)**（2026-04-09，2604.08014v3）：本文提出Bridge-STG，一种端到端的解耦式时空视频定位框架，通过时空语义桥接机制（STSB）和查询引导空间定位模块（QGSL）分别解决时空对齐纠缠和双域视觉token冗余问题，在VidSTG基准上将平均m_vIoU从26.4提升至34.3，达到MLLM-based方法的最优性能。
- **[SPARROW: Learning Spatial Precision and Temporal Referential Consistency in Pixel-Grounded Video MLLMs](http://arxiv.org/abs/2603.12382v1)**（2026-03-12，2603.12382v1）：SPARROW通过引入目标特定跟踪特征（TSF）和双提示（[BOX]+[SEG]）接地机制，统一了像素级视频MLLMs的空间精度与时间稳定性，在不依赖外部检测器的情况下实现了端到端的指代一致视频分割。

### 视频检索（5 篇）

- **[ReTrack: Evidence-Driven Dual-Stream Directional Anchor Calibration Network for Composed Video Retrieval](http://arxiv.org/abs/2604.17898v1)**（2026-04-20，2604.17898v1）：ReTrack是首个通过校准组合特征方向性偏差来提升多模态查询理解的CVR框架，利用语义贡献解耦、组合几何校准和可靠证据驱动对齐三个模块，在CVR和CIR任务上均达到SOTA性能。
- **[ViLL-E: Video LLM Embeddings for Retrieval](http://arxiv.org/abs/2604.12148v1)**（2026-04-13，2604.12148v1）：ViLL-E提出了一种统一的VideoLLM架构，通过引入新颖的嵌入生成机制（EOS触发的自适应计算）和三阶段联合生成-对比训练方法，使单个模型同时具备文本生成和视频/文本嵌入生成能力，在时间定位和视频检索任务上达到与专家模型相当的性能，同时保持VideoQA竞争力。
- **[EagleNet: Energy-Aware Fine-Grained Relationship Learning Network for Text-Video Retrieval](http://arxiv.org/abs/2603.25267v3)**（2026-03-26，2603.25267v3）：EagleNet通过构建文本-帧关系图并引入能量感知匹配机制，在扩展文本语义时同时建模文本-帧交互和帧间关系，生成上下文感知的富文本嵌入，从而提升文本-视频检索的精度。
- **[Unbiased Multimodal Reranking for Long-Tail Short-Video Search](http://arxiv.org/abs/2603.24975v2)**（2026-03-26，2603.24975v2）：本文提出一个由LLM驱动的多模态重排序框架，通过两阶段训练（监督微调+成对偏好优化）学习用户行为无关的体验评分，并将其注入生产级重排序流水线以缓解长尾短视频搜索中的多种偏差。
- **[CoVR-R:Reason-Aware Composed Video Retrieval](http://arxiv.org/abs/2603.20190v2)**（2026-03-20，2603.20190v2）：本文提出了一种推理优先的零样本组合视频检索方法CoVR-R，利用大型多模态模型（Qwen3-VL-8B）推断编辑隐含的因果和时间后效，并将其转化为效果感知查询来指导检索，同时构建了CoVR-Reason基准测试来评估推理能力，在无需任务特定微调的情况下显著优于强基线方法。

### 视频异常检测（1 篇）

- **[MMVIAD: Multi-view Multi-task Video Understanding for Industrial Anomaly Detection](http://arxiv.org/abs/2605.10833v1)**（2026-05-11，2605.10833v1）：该论文提出了MMVIAD——首个用于工业异常检测与理解的连续多视角视频数据集及基准，并开发了VISTA两阶段后训练流水线（PS-SFT初始化 + VISTA-GRPO强化学习优化），显著提升了视频多模态大语言模型在异常检测、缺陷分类、物体分类和异常可见时间定位四个耦合任务上的表现。

### 时序动作定位（1 篇）

- **[OZ-TAL: Online Zero-Shot Temporal Action Localization](http://arxiv.org/abs/2605.09976v1)**（2026-05-11，2605.09976v1）：论文提出在线零样本时序动作定位（OZ-TAL）这一新任务，并设计了一个基于预训练视觉-语言模型的无训练框架VFEAL，通过记忆引导特征增强、背景感知k-way分类和在线动作跨度预测，在THUMOS14和ActivityNet-1.3上显著超越现有最先进方法。

## 对方案的直接影响

- **第一阶段召回**：保留双编码器/Video-LLM embedding + ANN 索引；针对组合查询和长尾查询，
  增加专门重排器，不让大模型逐库扫描。
- **第二阶段定位**：采用支持多 proposal、开放集拒答和条件多事件的 VMR/VTG 模型，输出一个或
  多个 `[start, end]`，同时给出无匹配置信度。
- **长视频处理**：查询到来后动态选帧、裁剪 clip 或折叠 token；离线维护镜头、事件、对象和
  ASR/OCR 多粒度索引，避免固定均匀采样。
- **结果验证**：把候选时间段交给 Video-LLM 做 plan/propose-verify，并返回原始帧、人物轨迹、
  OCR/ASR 与场景图证据，减少只给自然语言答案的幻觉。
- **评测**：除 Recall@K、mAP、R@1@tIoU 外，增加无效查询拒答、跨域、长尾、证据充分性、
  延迟与显存/吞吐指标。

## 预期可实现效果

组合上述论文方向后，系统可以实现自然语言检索视频、定位事件起止时间、返回多个相关片段、
对长视频进行证据式问答，以及对无匹配查询给出拒答。近期最现实的形态是“高召回候选发现 +
时间段定位 + 证据预览 + 人工复核”；月级记忆、复杂因果链、跨摄像头身份一致性和行为意图判断
仍是明显短板，不能只依赖公开基准分数承诺线上效果。

## 本地成果位置

- 综合数据集与工程方案：`data/video_search_model_dataset_summary.md`
- 50 篇论文元数据清单：`data/search_candidates.json`
- 逐篇完整中文总结：`docs/paper-data/details/<arxiv-id>.json`
- 视频检索专题页：`docs/video-search.html`
- 本地数据库与 PDF：`data/papers.db`、`data/pdfs/`（运行时数据，不提交 Git）

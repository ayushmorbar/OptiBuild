---
config:
  layout: elk
---
flowchart TB
 subgraph s1["OR Problem Modelisation"]
        C1["1a - DECISION VARIABLES<br>Which components / attributes are in play?<br>(cpu, gpu, price, noise...)"]
        C2["1b - DERIVED VARIABLES<br>functions of decision variables<br>(total price, total power, total noise...)"]
        D["2 - OBJECTIVES<br>Among the variables, which to max/min?<br>plus weights (price down, noise down)"]
        E["3 - CONSTRAINTS<br>Hard thresholds on those variables<br>(BO7 to min GPU/CPU/RAM, compatibility)"]
  end
    A["Input: free-form request"] --> B["Orchestrator Agent"]
    B --> C1
    C1 --> C2
    C2 --> D
    D --> E
    E --> F["Defines the pivot schema<br>variables, constraints, objectives<br>(Pydantic)"]
    F --> EVAL{"EVALUATOR<br>score the modelisation:<br>completeness, coherence,<br>intent fidelity"}
    EVAL -- below threshold --> FB["Structured feedback<br>missing vars / conflicts / intent gap"]
    FB --> B
    EVAL -- pass --> n2["Fetch Data<br>/fetch_data skill search appropriate CSV<br>-&gt; return satisfied **deicsion variables**"]
    G["Translate specs to numeric thresholds<br>(knowledge base)"] --> H["PRE-FILTER components (pandas)<br>drop parts below hard thresholds"]
    H --> I["SOLVER CP-SAT: assemble valid builds"]
    H -.- NOTE1["NOTE: Only single-component rules<br>- Single components who doesnt match with the goal"]
    I --> J{"Number of objectives?"}
    J -- 1 --> K["CP-SAT optimizes directly"]
    K --> N["Output: recommended config"]
    M["TOPSIS (pymcdm): rank"] --> N
    I -.- NOTE2["NOTE :.<br>It CONSTRUCTS valid builds by picking one part per category<br>while enforcing compatibility and budget.<br>"]
    J -- "&gt;=2" --> n1["Define Weights that align with the user goal"]
    n1 --> M
    n2 -.- n3["NOTE :<br>For the V1, only seek trough a PC Components dataset. metadata attached to a CSV to help the agent finding correct data<br>Meta Data must contain a description and columns available.<br>Use Rag system if too many CSV."]
    n2 --> n9["DATA :All decision variables satisfied by data ?"]
    n4["START"] --> A
    n5["Systematic data cleaning<br>"] -.- n6["NOTE :<br>Systematic necessary cleaning<br>- clean data (negative prices, extreme values...)<br>- user query related cleaning"]
    n5 --> n7["Dynamic data cleaning"]
    n7 --> G
    n7 -.- n8["NOTE :<br>Depennds on the user prompt<br>LLM queries the dataframe."]
    n9 -- YES --> n5
    n9 -- NO --> n10["DATA : Missing satisfied decision variable who defines a constraint / goal ?"]
    n10 -- NO --> n5
    n10 -- YES --> FB
    n10 -.- n11["NOTE :<br>If in we have missing data necessary to define constraints /L goals, we must inform the user"]
    N --> n13["Found a config ?"]
    n13 -- YES --> n15["Return result to user UI"]
    n15 --> n16["END"]
    n13 -- NO --> FB

    n1@{ shape: proc}
    n3@{ shape: proc}
    n9@{ shape: diam}
    n4@{ shape: rect}
    n10@{ shape: diam}
    n13@{ shape: diam}
    style C1 fill:#FFCDD2
    style C2 fill:#FFCDD2
    style D fill:#FFCDD2
    style E fill:#FFCDD2
    style A stroke:#757575,fill:#757575,color:#ffffff
    style F fill:#4a5568,color:#fff
    style EVAL fill:#dd6b20,color:#fff
    style FB fill:#fbd38d,color:#5c2e00
    style n2 fill:#E1BEE7
    style I fill:#2b6cb0,color:#fff
    style NOTE1 fill:#fff3b0,stroke:#d4a017,color:#5c4400
    style M fill:#2f855a,color:#fff
    style NOTE2 fill:#fff3b0,stroke:#d4a017,color:#5c4400
    style n3 stroke:#d4a017,fill:#fff3b0
    style n4 fill:#2f855a,stroke:#00C853,color:#ffffff
    style n6 fill:#fff3b0,stroke:#d4a017
    style n8 stroke:#d4a017,fill:#fff3b0
    style n11 stroke:#dd6b20,fill:#fff3b0
    style n16 stroke:#D50000,fill:#D50000,color:#ffffff
    style s1 fill:transparent,stroke:#000000

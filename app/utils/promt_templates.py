# app/utils/prompt_templates.py

SESSION_SUMMARY_PROMPT = """
You are an expert clinical(Theraputic) assistant.

Given the full conversation transcription between a therapist and a client,
write a clear, concise, neutral, clinically useful session summary.

Requirements:
- The summary must include the key points discussed during the session.
- Use professional and neutral language.
- Avoid any subjective opinions or interpretations.
- Length: Aim for 150-200 words only if the conversation is long enough else make it concise.
- You can add information like the confidence level, anxiety level, mood, and other relevant clinical observations based on the conversation but they must be relevant.
- Don't add the Markdown formatting.

Here is the full transcription:

{transcription_text}
"""

SENTIMENT_ANALYSIS_PROMPT = """
You are an expert clinical psychologist AI analyzing a therapy session transcription.

**Task:**
Analyze the emotional tone and sentiment of the **client's utterances only**. The therapist's words should provide context but should NOT influence the sentiment score directly.

**Context:**
This is a conversation between a Therapist and a Client. You must differentiate between them based on the speaker labels or context cues if labels are missing.

**Scoring Criteria:**
Provide a single sentiment score ranging from -1.00 (Extremely Negative/Distressed) to +1.00 (Extremely Positive/Stable).
- **-1.0 to -0.6**: Severe distress, suicidal ideation, crisis, hopelessness, or intense anger.
- **-0.5 to -0.2**: Anxiety, sadness, frustration, confusion, or general struggle.
- **-0.1 to +0.1**: Neutral, calm, or factual recounting of events without strong emotion.
- **+0.2 to +0.5**: Hopeful, insightful, making progress, expressing gratitude or relief.
- **+0.6 to +1.0**: Joyful, stable, celebrating success, or expressing deep satisfaction.

**Output Format:**
You may provide a brief (1 sentence) explanation of your reasoning, but you **MUST** end your response with the exact string "SENTIMENT_SCORE:" followed by the number.

Example Response:
The client expressed significant anxiety about their job but showed hope regarding their relationship progress.
SENTIMENT_SCORE: -0.25

**Transcription:**
{transcription_text}
"""

THEME_EXTRACTION_PROMPT = """
You are an expert Clinical Supervisor analyzing a therapy session transcription.

**Task:**
Identify the **Primary Clinical Theme** of this session. You must select **EXACTLY ONE** theme from the list below.
Once you identify the theme, you must output the corresponding **Standard Explanation** provided in the list. Do not write your own explanation.

**List of Themes & Standard Explanations:**

1. **Intake & Diagnosis**
   Standard Explanation: Focused on initial assessment, history taking, symptom review, and diagnostic formulation.

2. **Rapport Building**
   Standard Explanation: Focused on establishing the therapeutic alliance, building trust, and setting boundaries.

3. **Crisis Intervention**
   Standard Explanation: Focused on managing acute risks, safety planning, de-escalation, or immediate stabilization.

4. **Psychoeducation**
   Standard Explanation: Focused on teaching the client about mental health conditions, symptoms, or brain function.

5. **Cognitive Restructuring**
   Standard Explanation: Focused on identifying and challenging cognitive distortions, automatic thoughts, or reframing.

6. **Behavioral Activation**
   Standard Explanation: Focused on scheduling positive activities to combat depression, lethargy, or withdrawal.

7. **Exposure Therapy**
   Standard Explanation: Focused on systematic desensitization or facing feared stimuli and situations.

8. **Emotional Regulation**
   Standard Explanation: Focused on teaching skills to manage intense affect, anger, panic, or distress tolerance.

9. **Mindfulness & Grounding**
   Standard Explanation: Focused on practicing present-moment awareness, breathing, or anchoring techniques.

10. **Trauma Processing**
    Standard Explanation: Focused on discussing past traumatic events, PTSD symptoms, or narrative exposure work.

11. **Grief & Loss**
    Standard Explanation: Focused on processing bereavement, separation, job loss, or significant life transitions.

12. **Interpersonal Effectiveness**
    Standard Explanation: Focused on discussing communication skills, assertiveness, or social interactions.

13. **Relationship/Couples Work**
    Standard Explanation: Focused on addressing romantic partnership dynamics, infidelity, or intimacy issues.

14. **Family Dynamics**
    Standard Explanation: Focused on exploring family-of-origin issues, parenting struggles, or systemic conflicts.

15. **Identity & Self-Esteem**
    Standard Explanation: Focused on exploring self-worth, core beliefs, personal values, or imposter syndrome.

16. **Insight & Exploration**
    Standard Explanation: Focused on psychodynamic exploration of unconscious patterns or root causes.

17. **Substance Use & Recovery**
    Standard Explanation: Focused on addressing addiction, cravings, relapse prevention, or harm reduction.

18. **Habit Change**
    Standard Explanation: Focused on working on impulse control, procrastination, eating behaviors, or discipline.

19. **Sleep & Somatic Issues**
    Standard Explanation: Focused on addressing insomnia, chronic pain, or the body-mind connection.

20. **Motivation & Goal Setting**
    Standard Explanation: Focused on Motivational Interviewing, clarifying ambivalence, or setting SMART goals.

21. **Existential & Meaning**
    Standard Explanation: Focused on discussing purpose, mortality, spirituality, or life direction.

22. **Work & Academic Stress**
    Standard Explanation: Focused on addressing burnout, career changes, or performance anxiety.

23. **Acceptance Strategies**
    Standard Explanation: Focused on practicing radical acceptance or willingness to experience difficult emotions.

24. **Parts Work**
    Standard Explanation: Focused on exploring internal conflict, the inner child, or distinct self-states.

25. **Social Skills Training**
    Standard Explanation: Focused on role-playing or coaching on social cues and connection.

26. **Attachment Repair**
    Standard Explanation: Focused on working on attachment styles and security in relationships.

27. **Perinatal & Reproductive Mental Health**
    Standard Explanation: Focused on issues related to pregnancy, postpartum, infertility, or loss.

28. **Cultural & Social Justice**
    Standard Explanation: Focused on discussing impacts of discrimination, acculturation, or systemic oppression.

29. **Progress Review**
    Standard Explanation: Focused on evaluating treatment gains, celebrating milestones, or maintenance planning.

30. **Termination & Closure**
    Standard Explanation: Focused on discussing the end of therapy, relapse prevention planning, and goodbyes.

**Output Format:**
You must strictly follow this format. Do not use Markdown (bolding/italics).

THEME: [Exact Theme Name]
EXPLANATION: [Exact Standard Explanation provided above]

**Transcription:**
{transcription_text}
"""
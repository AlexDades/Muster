"""
One-shot evaluation script. Runs 25 questions through the live RAG pipeline,
scores each answer against the expected answer using Claude, then prints a report.
"""
import sys
import textwrap
import anthropic
from app.config import settings
from app.indexer.store import PolicyStore
from app.retrieval.pipeline import answer_question

QA_PAIRS = [
    (
        "so like if i have 7 days left at the end of the year, what happens to it? can i like keep it or does the company steal my time?",
        "Only 5 days can be rolled over to the following calendar year. The remaining 2 days (exceeding the 5-day maximum) will be forfeited on December 31st.",
    ),
    (
        "my manager said sick days stack up like PTO but im pretty sure thats wrong? whats the actual deal with carrying over sick leave?",
        "Correct, your manager is wrong. Sick leave does not accrue and does not carry over to the following year. Employees get 10 fresh days per year, and any unused days are lost at year-end.",
    ),
    (
        "ive been here 5 months, can i work from home? or do i gotta wait another month?",
        "No, you cannot work from home yet. Remote work eligibility requires completing a 6-month probationary period. You need to wait 1 more month. Additionally, your role would need to be suitable for remote work, as determined by your manager and HR.",
    ),
    (
        "if theyre making us come in on a holiday, when do we get our day off? can it be like 3 months later or does it have to be soon?",
        "The company will provide a day in lieu within 30 days of the public holiday you worked. It must be taken within that 30-day window, not 3 months later.",
    ),
    (
        "how long can i be out sick before i need to get a doctor note? is it 3 days or 4 days?",
        "A medical certificate is required for absences exceeding 3 consecutive days. This means if you're absent for 4 or more consecutive days, you need a medical certificate. Being out for 3 days or fewer does not require one.",
    ),
    (
        "im in a different timezone, does the 10am-3pm thing still apply to me or is it like... different?",
        "Core hours are 10:00 AM to 3:00 PM in your local time zone, not the company's time zone. So yes, it still applies, but it's based on where you are located.",
    ),
    (
        "do i really need vpn for like everything when im working from home, or just for important stuff?",
        "You must use the company VPN whenever accessing internal company systems, databases, or confidential information remotely. Additionally, employees must not use public Wi-Fi without the VPN at all—so yes, it's required for anything work-related when not on a secure connection.",
    ),
    (
        "so im allowed 3 days remote right? that means i could do like 2 weeks of remote if i bank my days, yeah?",
        "No. You can work remotely up to 3 days per week, but this is a weekly limit, not something that accumulates. You cannot bank remote days to take longer stretches away from the office. Additionally, you must work at least 2 days per week from the office.",
    ),
    (
        "the company gives 30 euros for internet. does that cover like all my home tech expenses?",
        "No. The EUR 30 monthly stipend is specifically to offset home internet costs only. It does not cover other home technology expenses or equipment beyond what the company provides (which is a laptop).",
    ),
    (
        "i just finished my first 3 months here, can i take pto next week?",
        "No, not yet. You need to complete the 90-day probationary period before you can begin using PTO. If you've just completed 3 months, you're technically at the 90-day mark—you should confirm with HR—but you cannot use it before completing the full probationary period.",
    ),
    (
        "if i quit tomorrow, do i definitely lose all my saved up vacation days?",
        "Not necessarily. Upon normal termination, you will be paid out for accrued but unused PTO. However, if you resign without providing adequate notice (as determined by the company), the company may forfeit your accrued PTO at their discretion. It depends on whether you provide adequate notice.",
    ),
    (
        "can i use my sick days for like a mental health day if im not physically sick?",
        "The policy does not explicitly address this. However, the policy defines sick leave as 10 days per year separate from PTO. The policy as written is silent on whether mental health days qualify, but they would likely need to follow the same medical certificate requirements if exceeding 3 consecutive days.",
    ),
    (
        "once i start working from home, is that like permanent or can they take it away?",
        "It is not permanent. Remote work is explicitly stated as a privilege, not a right. If your performance declines or the arrangement creates business problems, your manager may require you to return to full-time office work. Remote work arrangements are reviewed annually, meaning they can be revoked.",
    ),
    (
        "can i pick like monday, wednesday, and friday for remote, or does it gotta be consecutive days?",
        "The policy does not require remote days to be consecutive. You can work remotely up to 3 days per week, and the specific days must be agreed in advance with your manager. So Monday, Wednesday, Friday would be acceptable if your manager approves.",
    ),
    (
        "im part time working like half the hours. do i get half the pto or something else?",
        "Yes. Part-time employees receive PTO on a pro-rated basis. So if you work 50% of full-time hours, you would accrue approximately 7.5 days of PTO per year (50% of 15 days).",
    ),
    (
        "if i hurt myself at home while working remote, the company has to pay for it right?",
        "No. The company is not liable for injuries that occur in a non-compliant home workspace. Employees are responsible for ensuring their remote workspace is safe and ergonomically appropriate. The company may require a home workspace assessment to verify compliance.",
    ),
    (
        "how much notice do i gotta give for like a week off? is it a week? 2 weeks?",
        "For 3 or more consecutive days (which would include a full week), you must submit requests at least 2 weeks in advance via the HR portal. The policy requires 2 weeks, not 1 week.",
    ),
    (
        "if im out for 4 days, when do i need to show the doctors note? on day 4 or when i come back?",
        "The policy requires a medical certificate for absences exceeding 3 consecutive days but does not specify the exact timing for when it must be submitted. Based on standard practice, it should be submitted when returning to work or as soon as possible, but the policy doesn't explicitly state this.",
    ),
    (
        "the policy says meetings should be during core hours. what if my manager schedules something outside those times?",
        "The policy states meetings should be scheduled during core hours where possible, which provides some flexibility. However, employees must still be available and responsive during core hours of 10:00 AM to 3:00 PM. A meeting scheduled outside core hours would conflict with this requirement. Employees should push back and request rescheduling during core hours.",
    ),
    (
        "if the company gives me a laptop, do i still gotta buy my own laptop for remote work or can i use a personal computer?",
        "The company provides a laptop for all employees, and that's what you should use for remote work. The policy emphasizes security requirements including using the company VPN and keeping company devices physically secure. Using a personal computer for work is not mentioned and would raise security concerns, so you should use the company-provided laptop.",
    ),
    (
        "can i take sick days spread out like monday one week and friday another, or do they gotta be back to back?",
        "The policy does not prohibit non-consecutive sick days. The medical certificate requirement specifically applies to absences exceeding 3 consecutive days, implying that non-consecutive days are treated differently. You can take individual sick days scattered throughout the year.",
    ),
    (
        "if i work 3 days remote and get 2 office days, like... can i just go home early on office days?",
        "No. The policy requires that at least 2 days per week are worked from the office. This means you must be physically present in the office for those days during your working hours. Additionally, core hours (10 AM - 3 PM) must be maintained. You cannot leave early or count a partial day as office presence without manager approval.",
    ),
    (
        "do i earn pto during my probation period even though i cant use it til after?",
        "The policy states employees may begin using PTO after completing their 90-day probationary period but does not explicitly state whether PTO is accrued during probation. Based on standard practice, they likely accrue it but cannot use it, so it would be available after probation ends. However, this is ambiguous in the policy.",
    ),
    (
        "if im scheduled to work a public holiday but im supposed to be remote that day, do i go to the office or stay home?",
        "The policy does not explicitly address this scenario. If you're required to work a public holiday, the general expectation would be to work (either remotely or in-office as directed), and you'd receive a day in lieu within 30 days. You should clarify with your manager whether remote work is acceptable on that day.",
    ),
    (
        "its december 20th and im trying to request like 2 days remote work next week, is that allowed or too late?",
        "The remote work policy does not specify a notice period for scheduling remote days. However, it states the specific days must be agreed in advance with the employee's manager. One week's notice for requesting remote work days seems reasonable and would likely be acceptable, but you'd need to get explicit approval from your manager.",
    ),
]

JUDGE_PROMPT = """\
You are evaluating an AI assistant's answer to an HR policy question.

Question: {question}

Expected answer (ground truth):
{expected}

Model's actual answer:
{actual}

Score the model's answer on a scale of 1 to 3:
1 = Wrong or missing a key fact from the expected answer
2 = Partially correct — gets the gist but omits or misstates something material
3 = Fully correct — covers all key facts from the expected answer accurately

Reply with ONLY a JSON object in this exact format (no other text):
{{"score": <1|2|3>, "reason": "<one sentence>"}}
"""


def score_answer(client: anthropic.Anthropic, question: str, expected: str, actual: str) -> dict:
    import json, re
    prompt = JUDGE_PROMPT.format(question=question, expected=expected, actual=actual)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    # Extract JSON even if wrapped in markdown code fences
    match = re.search(r'\{.*?\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return {"score": 2, "reason": f"could not parse judge response: {raw[:80]}"}


def main():
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    store = PolicyStore(
        db_path=settings.chroma_db_path,
        collection_name=settings.collection_name,
    )

    results = []
    print(f"Running {len(QA_PAIRS)} questions through the RAG pipeline...\n")

    for i, (question, expected) in enumerate(QA_PAIRS, 1):
        print(f"  Q{i:02d}...", end=" ", flush=True)
        try:
            result = answer_question(question, store, client=client)
            actual = result["answer"]
        except Exception as e:
            actual = f"[ERROR: {e}]"
            results.append({"q": i, "question": question, "expected": expected,
                            "actual": actual, "score": 1, "reason": "pipeline error"})
            print("ERROR")
            continue

        judgment = score_answer(client, question, expected, actual)
        results.append({
            "q": i,
            "question": question,
            "expected": expected,
            "actual": actual,
            "score": judgment["score"],
            "reason": judgment["reason"],
        })
        print(f"score={judgment['score']}")

    # Summary
    total = len(results)
    max_score = total * 3
    achieved = sum(r["score"] for r in results)
    pct = round(achieved / max_score * 100, 1)

    perfect = [r for r in results if r["score"] == 3]
    partial = [r for r in results if r["score"] == 2]
    wrong   = [r for r in results if r["score"] == 1]

    print(f"\n{'='*60}")
    print(f"ACCURACY: {pct}%  ({achieved}/{max_score} points)")
    print(f"  Full marks (3/3): {len(perfect)}/{total}")
    print(f"  Partial   (2/3): {len(partial)}/{total}")
    print(f"  Wrong     (1/3): {len(wrong)}/{total}")

    if partial or wrong:
        print(f"\n{'='*60}")
        print("ANSWERS THAT COULD BE BETTER:\n")
        for r in partial + wrong:
            label = "PARTIAL" if r["score"] == 2 else "WRONG"
            print(f"Q{r['q']:02d} [{label}] — {r['reason']}")
            print(f"  Question : {r['question'][:80]}...")
            print(f"  Expected : {r['expected'][:120]}...")
            print(f"  Got      : {r['actual'][:120]}...")
            print()


if __name__ == "__main__":
    main()

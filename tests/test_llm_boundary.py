from fermion.cognitive.llm import contains_unverified_claim, extract_final_answer


def test_qwen_thinking_output_exposes_only_final_answer() -> None:
    reasoning, answer = extract_final_answer("<think>private chain</think>Hello from FERMiON.")
    assert reasoning == "private chain"
    assert answer == "Hello from FERMiON."


def test_incomplete_qwen_thinking_is_not_a_user_answer() -> None:
    reasoning, answer = extract_final_answer("<think>unfinished private chain")
    assert reasoning == ""
    assert answer == ""


def test_unverified_execution_and_memory_claims_are_rejected() -> None:
    assert contains_unverified_claim("I executed the script and verified exit status 0.")
    assert contains_unverified_claim("The value was retrieved from persistent memory with memory_id mem_fake.")
    assert not contains_unverified_claim("I can help explain the result once FERMiON supplies a receipt.")
    assert not contains_unverified_claim("I did not execute code because no structured evidence was available.")
    assert contains_unverified_claim("Python execution: the root-finding result passed all checks.")

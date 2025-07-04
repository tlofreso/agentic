import asyncio
import random
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import re

from pydantic import BaseModel, Field
from agents import (
    Agent,
    Runner,
    InputGuardrail,
    GuardrailFunctionOutput,
    RunContextWrapper,
    TResponseInputItem,
    trace
)

# Pydantic Models
class PlaceholderType(str, Enum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"

class VerbList(BaseModel):
    verbs: List[str] = Field(
        description="List of unique verbs in base form",
        min_length=5,
        max_length=5
    )

class AdjectiveList(BaseModel):
    adjectives: List[str] = Field(
        description="List of unique adjectives",
        min_length=5,
        max_length=5
    )

class Placeholder(BaseModel):
    id: int
    type: PlaceholderType
    filled_value: Optional[str] = None

class MadlibTemplate(BaseModel):
    topic: str
    template_text: str = Field(description="The madlib template with placeholders marked as {noun_1}, {verb_1}, etc.")
    placeholders: List[Placeholder]
    created_at: datetime = Field(default_factory=datetime.now)

class CompletedMadlib(BaseModel):
    topic: str
    template_text: str
    filled_text: str
    placeholders: List[Placeholder]
    created_at: datetime
    completed_at: datetime = Field(default_factory=datetime.now)

# Guardrail for family-friendly content
class ContentCheckResult(BaseModel):
    is_family_friendly: bool
    reasoning: str

content_check_agent = Agent(
    name="Content Checker",
    instructions="""Check if the given topic is family-friendly.
    Topics containing violence, adult content, profanity, drugs,
    or other inappropriate content should be marked as not family-friendly.""",
    output_type=ContentCheckResult,
)

async def family_friendly_guardrail(
    ctx: RunContextWrapper[None], agent: Agent, input: str | list[TResponseInputItem]
) -> GuardrailFunctionOutput:
    """Check if the topic is family-friendly."""
    result = await Runner.run(content_check_agent, str(input), context=ctx.context)
    final_output = result.final_output_as(ContentCheckResult)

    return GuardrailFunctionOutput(
        output_info=final_output,
        tripwire_triggered=not final_output.is_family_friendly,
    )

# Template Generator Agent
template_generator_agent = Agent(
    name="Template Generator",
    instructions="""Create a fun, engaging madlib template for the given topic.
    - Keep it under 150 words
    - Include EXACTLY 15 fill-in placeholders: 5 nouns, 5 verbs, and 5 adjectives
    - Use placeholders in this exact format: {noun_1}, {noun_2}, {noun_3}, {noun_4}, {noun_5},
      {verb_1}, {verb_2}, {verb_3}, {verb_4}, {verb_5},
      {adjective_1}, {adjective_2}, {adjective_3}, {adjective_4}, {adjective_5}
    - Make sure to use ALL 15 placeholders in your template
    - Make it entertaining and appropriate for all ages""",
    output_type=MadlibTemplate,
)

# Word Generation Agents
verb_agent = Agent(
    name="Verb Generator",
    instructions="""Generate exactly 5 unique verbs in their base form.
    - Make them varied and interesting
    - Keep them family-friendly
    - Ensure all 5 are completely different from each other
    - Mix action types (movement, communication, creation, etc.)
    Just provide the verbs, no context or explanation.""",
    output_type=VerbList,
)

adjective_agent = Agent(
    name="Adjective Generator",
    instructions="""Generate exactly 5 unique adjectives.
    - Make them varied and interesting (mix colors, textures, emotions, sizes, etc.)
    - Keep them family-friendly
    - Ensure all 5 are completely different from each other
    - Avoid repetitive patterns (like all ending in -ous or -ful)
    Just provide the adjectives, no context or explanation.""",
    output_type=AdjectiveList,
)
# Noun Validation
class NounValidationResult(BaseModel):
    is_noun: bool
    reasoning: str

noun_validator_agent = Agent(
    name="Noun Validator",
    instructions="""Check if the given word is primarily a noun.
    Be very strict:
    - Reject words that are primarily verbs like: jump, run, fight, fly, swim, eat, sleep
    - Reject words that are primarily adjectives like: happy, sad, big, small
    - Accept only words that are clearly nouns like: car, house, person, tree, book, computer, dog, cat, sword, stone, pool
    - If a word CAN be used as a noun but is MORE COMMONLY used as another part of speech, reject it
    For example, 'fight' CAN be a noun (as in 'a fight') but is primarily a verb, so reject it.""",
    output_type=NounValidationResult,
)

async def validate_noun(word: str) -> bool:
    """Validate if a word is actually a noun."""
    result = await Runner.run(noun_validator_agent, f"Is '{word}' a noun?")
    validation = result.final_output_as(NounValidationResult)
    return validation.is_noun

async def mock_save_madlib(madlib: CompletedMadlib) -> Dict[str, str]:
    """Mock REST API call to save the completed madlib."""
    print("\n[MOCK REST CALL] Saving madlib to external system...")
    print("Endpoint: POST https://api.madlibs.example.com/v1/madlibs")
    print(f"Payload: {madlib.model_dump_json(indent=2)}")
    return {"status": "success", "id": f"madlib_{random.randint(1000, 9999)}"}

async def get_user_noun(noun_number: int) -> str:
    """Get a noun from the user with validation."""
    while True:
        noun = input(f"Please enter noun #{noun_number}: ").strip()
        if await validate_noun(noun):
            return noun
        else:
            print(f"'{noun}' is not a valid noun. Please try again.")

async def fill_madlib_template(template: MadlibTemplate) -> CompletedMadlib:
    """Fill in the madlib template with words."""

    placeholder_pattern = r'\{(noun|verb|adjective)_(\d+)\}'
    found_placeholders = re.findall(placeholder_pattern, template.template_text)

    # Create organized lists of what we need
    noun_numbers = sorted(set(int(num) for ptype, num in found_placeholders if ptype == 'noun'))
    verb_numbers = sorted(set(int(num) for ptype, num in found_placeholders if ptype == 'verb'))
    adj_numbers = sorted(set(int(num) for ptype, num in found_placeholders if ptype == 'adjective'))

    # Create a mapping for replacements
    placeholder_map = {}

    # Create tasks for parallel processing
    async def get_nouns():
        for num in noun_numbers:
            noun = await get_user_noun(num)
            placeholder_map[f"{{noun_{num}}}"] = noun

    async def get_verbs():
        if verb_numbers:
            result = await Runner.run(verb_agent, f"Generate {len(verb_numbers)} verbs")
            verb_list = result.final_output_as(VerbList)
            for num, verb in zip(verb_numbers, verb_list.verbs):
                placeholder_map[f"{{verb_{num}}}"] = verb

    async def get_adjectives():
        if adj_numbers:
            result = await Runner.run(adjective_agent, f"Generate {len(adj_numbers)} adjectives")
            adj_list = result.final_output_as(AdjectiveList)
            for num, adj in zip(adj_numbers, adj_list.adjectives):
                placeholder_map[f"{{adjective_{num}}}"] = adj

    # Run in parallel
    print("\n🎯 Let's fill in your madlib!")
    print(f"I need {len(noun_numbers)} nouns from you.\n")

    await asyncio.gather(
        get_nouns(),
        get_verbs(),
        get_adjectives()
    )

    # Fill in the template using the mapping
    filled_text = template.template_text
    for placeholder_key, value in placeholder_map.items():
        filled_text = filled_text.replace(placeholder_key, value)

    # Rebuild placeholders list with correct data
    placeholders = []
    placeholder_id = 1

    for ptype, num in found_placeholders:
        placeholder_type = PlaceholderType(ptype)
        key = f"{{{ptype}_{num}}}"
        placeholders.append(Placeholder(
            id=placeholder_id,
            type=placeholder_type,
            filled_value=placeholder_map.get(key, "")
        ))
        placeholder_id += 1

    return CompletedMadlib(
        topic=template.topic,
        template_text=template.template_text,
        filled_text=filled_text,
        placeholders=placeholders,
        created_at=template.created_at
    )

# Main orchestrator with guardrail
orchestrator_agent = Agent(
    name="Madlib Orchestrator",
    instructions="Coordinate the madlib generation process.",
    input_guardrails=[
        InputGuardrail(guardrail_function=family_friendly_guardrail)
    ],
)

async def main():
    """Main function to run the madlib generator."""
    print("🎭 Welcome to the AI Madlib Generator! 🎭\n")

    # Get topic from user
    topic = input("What topic would you like for your madlib? ").strip()

    with trace("Madlib Generation"):
        try:
            # Check if topic is family-friendly (via guardrail)
            await Runner.run(orchestrator_agent, topic)

            # Generate template
            print(f"\n✨ Creating a madlib about '{topic}'...")
            template_result = await Runner.run(template_generator_agent, f"Create a madlib template about: {topic}")
            template = template_result.final_output_as(MadlibTemplate)

            # Fill in the madlib
            completed_madlib = await fill_madlib_template(template)

            # Display the result
            print("\n📝 Your Completed Madlib:")
            print("-" * 50)
            print(completed_madlib.filled_text)
            print("-" * 50)

            # Mock save to external system
            save_result = await mock_save_madlib(completed_madlib)
            print(f"\n✅ Madlib saved successfully! ID: {save_result['id']}")

        except Exception as e:
            if "GuardrailTripwireTriggered" in str(type(e)):
                print(f"\n❌ Sorry, the topic '{topic}' is not appropriate for a family-friendly madlib.")
                print("Please try again with a different topic!")
            else:
                print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(main())

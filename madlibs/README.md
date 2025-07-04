Let's build an agentic system for generating madlibs. Keep in mind that the intent of this project is to showcase features that are included with the OpenAI Agents SDK.

We'll start by asking the user for a topic. Any topic that is not family friendly should be immediately rejected. Next, a madlib template will be generated considering the user's input. The requirements for the madlib template are as follows:

 - Should be short (fewer than 150 words)
 - Should be represented as a Pydantic model
 - Should include a minimum of 15 fill-ins

There will be an agent for providing Adjectives. There will be an agent for providing Verbs. Any Nouns will be provided by the user. Finally, the madlib that's produced will be saved to an external system via a REST call.

If there's ambiguity in any of these instructions, then ask for clarity. Let's begin.

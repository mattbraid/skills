# Summarize Text

**Source:** Claude  
**Category:** examples  
**Tags:** summarization, reading, productivity

## Purpose

Concisely summarize any piece of text, preserving the key points in plain language.

## Prompt / Instructions

```
Please summarize the following text in 3–5 bullet points. Focus on the most important ideas and keep each bullet to one sentence.

<text>
{{TEXT}}
</text>
```

## Example Input

> The Apollo program was a series of space missions undertaken by NASA with the goal of landing humans on the Moon. It ran from 1961 to 1972 and successfully landed twelve astronauts on the lunar surface across six missions, beginning with Apollo 11 in July 1969.

## Example Output

- NASA's Apollo program (1961–1972) aimed to land humans on the Moon.
- The program achieved its goal with six successful lunar landings.
- Twelve astronauts walked on the Moon in total.
- Apollo 11 in July 1969 was the first crewed lunar landing.

## Notes

- Replace `{{TEXT}}` with your content before sending.
- Works well with Claude 3 and GPT-4 class models.
- For very long documents, consider chunking the text first.

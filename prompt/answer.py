ANSWER_PROMPT = """---Role---
You are a helpful assistant responding to user query

---Goal---
Generate a concise response based on the following information and follow Response Rules. Do not include information not provided by following Information

---Target response length and format---
Multiple Paragraphs

---Information---
{{context}}

---Response Rules---
- Use markdown formatting with appropriate section headings
- Please respond in the same language as the user's question.
- If you don't know the answer, just say so.
- Do not make anything up. Do not include information not provided by the Infromation.

---Query---
{{question}}
"""
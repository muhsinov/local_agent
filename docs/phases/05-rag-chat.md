# Phase 5 - Grounded RAG Chat

- Retrieval oqimi: chat savoli vector search qiladi, topilgan chunklar context builder orqali yig'iladi va keyin Ollama promptiga qo'shiladi.
- Context assembly character budget bilan cheklanadi va source numbering deterministic `[1]`, `[2]` ko'rinishida bo'ladi.
- Citation formati faqat `brackets` style, response typed `sources` va `rag` metadata qaytaradi.
- Prompt-injection threat model: document content ishonchsiz material bo'lib, system instruction yoki tool request sifatida qabul qilinmaydi.
- Fallback behavior: index empty/dirty/busy/model unavailable holatlarida config ruxsat bersa non-RAG chatga qaytiladi.
- RAG yoqilgan/o'chirilgan rejim `use_rag` request fieldi va `RAG_ENABLED` config bilan boshqariladi.
- Index dirty yoki unavailable bo'lsa strict mode error, aks holda fallback mumkin.
- Hozir tool calling yo'q.
- Prompt character budget approximate bo'lib, exact tokenizer emas; priority safety system prompt, current user message, document context, newest history tartibida ishlaydi.
- Default budget estimate `4 chars/token`; answer generation uchun alohida reserve ajratiladi va actual tokenizer tilga qarab farq qilishi mumkin.
- Uzbek yoki Russian matnda estimate aniq bo'lmasligi mumkin, kerak bo'lsa konservativroq config ishlatiladi.
- History budgetdan oshsa eng eski xabarlar tushiriladi, context budgetdan oshsa final source excerpt qisqarishi mumkin.
- Markdown link va image label ichidagi `[1](...)`, `![1](...)` markerlar citation emas; invalid citation normalization multiline formattingni imkon qadar saqlaydi.

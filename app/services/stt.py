"""
STT (Speech-to-Text) service.
현재는 stub. ai.py의 transcribe_and_process에서 직접 호출됩니다.

TODO: 실제 구현 예시 (OpenAI Whisper)
    import openai, httpx
    async def transcribe(audio_url: str) -> str:
        async with httpx.AsyncClient() as client:
            audio_bytes = (await client.get(audio_url)).content
        oai = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        transcript = await oai.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.webm", audio_bytes, "audio/webm"),
        )
        return transcript.text
"""

# Интерфейсы и контракты

Сюда Opus записывает типы и сигнатуры перед каждой задачей. Исполнитель работает строго по этим интерфейсам — они фиксируют формат входных/выходных данных, сигнатуры функций и типы, на которые опирается стыковка между модулями.

## Пример

### AUTH-1: Авторизация
- `validateToken(token: string): { userId: string } | null`
- `createToken(userId: string, expiresIn: string): string`
- `UserPayload: { userId: string, email: string, role: string }`

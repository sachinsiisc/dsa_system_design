# Spring Framework & Microservices — Interview Master Guide

## Directory
```
Spring_Java/
├── 01_Spring_Core.md          ← IoC, DI, Beans, AOP
├── 02_Spring_Boot.md          ← Auto-config, Starters, Actuator
├── 03_Spring_MVC_REST.md      ← REST APIs, Controllers, Filters
├── 04_Spring_Data_JPA.md      ← Repositories, JPQL, Transactions
├── 05_Microservices.md        ← Patterns, Discovery, Gateway, Circuit Breaker
├── 06_Interview_QA.md         ← 60+ likely interview questions with answers
└── 07_Code_Examples.java      ← Runnable snippets for each concept
```

## What to know cold for a Java Backend interview

| Topic | Must-know depth |
|-------|----------------|
| `@Bean` vs `@Component` | ✅ Explain both, when to use each |
| `@Autowired` + injection types | ✅ Constructor vs field vs setter — prefer constructor |
| Spring Boot auto-config | ✅ How `@SpringBootApplication` works |
| REST controller full flow | ✅ Request → DispatcherServlet → Controller → Response |
| `@Transactional` propagation | ✅ REQUIRED, REQUIRES_NEW, NESTED |
| JPA — N+1 problem | ✅ Know the problem + fix (JOIN FETCH, @EntityGraph) |
| Microservices patterns | ✅ Service Discovery, API Gateway, Circuit Breaker, Saga |
| Eureka + Feign | ✅ How services register and call each other |
| Resilience4j Circuit Breaker | ✅ States: CLOSED / OPEN / HALF-OPEN |
| Docker + Spring Boot | ✅ Dockerfile, multi-stage build |

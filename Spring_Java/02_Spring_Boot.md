# 02 — Spring Boot: Auto-config, Starters, Actuator

---

## 1. What Spring Boot adds over Spring

| Spring (plain) | Spring Boot |
|---------------|-------------|
| You configure everything (XML or Java) | Auto-configures based on classpath |
| You manage versions | Starter POMs manage compatible versions |
| No built-in server | Embedded Tomcat/Jetty/Undertow |
| Manual setup | Opinionated defaults, override when needed |

---

## 2. `@SpringBootApplication` — What it actually does

```java
@SpringBootApplication  // this single annotation does 3 things:
public class MyApp {
    public static void main(String[] args) {
        SpringApplication.run(MyApp.class, args);
    }
}
```

It is shorthand for:
```java
@Configuration          // marks this as a config class
@EnableAutoConfiguration // enables auto-config magic
@ComponentScan          // scans current package + sub-packages for @Component beans
```

---

## 3. Auto-Configuration — How it works

**The key file:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Spring Boot ships with 100+ auto-configs. On startup:
1. Scans classpath for jars
2. Checks conditions (`@ConditionalOn*`)
3. Registers beans only if conditions pass

### Key Conditional annotations
```java
@ConditionalOnClass(DataSource.class)      // only if DataSource is on classpath
@ConditionalOnMissingBean(DataSource.class) // only if YOU haven't defined one
@ConditionalOnProperty("spring.datasource.url") // only if property is set
@ConditionalOnWebApplication               // only in a web app
```

### Example: DataSource auto-config (simplified)
```java
@Configuration
@ConditionalOnClass(DataSource.class)
@ConditionalOnProperty("spring.datasource.url")
public class DataSourceAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean  // won't override YOUR DataSource
    public DataSource dataSource(DataSourceProperties props) {
        return DataSourceBuilder.create()
            .url(props.getUrl())
            .username(props.getUsername())
            .password(props.getPassword())
            .build();
    }
}
```

**Key insight:** Spring Boot auto-config BACKS OFF if you define your own bean. Your config always wins.

---

## 4. Starters — Dependency bundles

Add one dependency → get all compatible transitive deps.

```xml
<!-- In pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <!-- pulls in: Spring MVC, Jackson, Tomcat, validation, logging -->
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
    <!-- pulls in: Hibernate, Spring Data, JDBC -->
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

---

## 5. `application.properties` / `application.yml`

```yaml
# application.yml
server:
  port: 8080

spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mydb
    username: user
    password: secret
  jpa:
    hibernate:
      ddl-auto: update   # validate | update | create | create-drop
    show-sql: true

logging:
  level:
    com.example: DEBUG
    org.hibernate.SQL: DEBUG
```

### Profiles
```yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:h2:mem:testdb  # in-memory for dev

# application-prod.yml
spring:
  datasource:
    url: jdbc:postgresql://prod-db:5432/mydb
```

Activate: `--spring.profiles.active=dev` or `SPRING_PROFILES_ACTIVE=prod`

### Custom properties
```yaml
app:
  max-retries: 3
  timeout: 5000
```

```java
@Component
@ConfigurationProperties(prefix = "app")
public class AppConfig {
    private int maxRetries;
    private long timeout;
    // getters/setters
}
```

Or simple:
```java
@Value("${app.max-retries:3}")  // with default
private int maxRetries;
```

---

## 6. Spring Boot Actuator

Exposes operational endpoints — health, metrics, info, env.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,env
  endpoint:
    health:
      show-details: always
```

Key endpoints:
| Endpoint | What it shows |
|----------|--------------|
| `/actuator/health` | App health + DB + disk |
| `/actuator/metrics` | JVM, HTTP, custom metrics |
| `/actuator/info` | App version, build info |
| `/actuator/env` | All properties/env vars |
| `/actuator/beans` | All registered beans |
| `/actuator/mappings` | All URL → controller mappings |

### Custom health indicator
```java
@Component
public class ExternalServiceHealth implements HealthIndicator {

    @Override
    public Health health() {
        boolean up = checkExternalService();
        return up ? Health.up().build()
                  : Health.down().withDetail("reason", "timeout").build();
    }
}
```

---

## 7. Spring Boot startup flow (interview question)

```
1. main() → SpringApplication.run()
2. Create ApplicationContext
3. Load @Configuration classes
4. ComponentScan → register @Component beans
5. Auto-configuration → register auto beans (conditional)
6. Wire dependencies (DI)
7. Run @PostConstruct methods
8. Start embedded Tomcat on configured port
9. App is ready — serving requests
```

---

## Interview Q&A — Spring Boot

**Q: What does `@SpringBootApplication` do?**
A: It's a shorthand for `@Configuration + @EnableAutoConfiguration + @ComponentScan`. It marks the entry point, enables auto-config, and scans the package tree for beans.

**Q: How does auto-configuration work?**
A: Spring Boot reads its auto-config classes. Each class has `@ConditionalOn*` annotations. If the condition is met (right class on classpath, right property set), the bean is registered — unless you've already defined one yourself.

**Q: What is a Starter?**
A: A curated Maven/Gradle dependency that brings in a set of compatible libraries. E.g., `spring-boot-starter-web` gives you Spring MVC + Jackson + Tomcat, all at compatible versions.

**Q: How to run different configs in dev vs prod?**
A: Spring Profiles. Use `application-dev.yml` and `application-prod.yml`, activate with `--spring.profiles.active=prod`.

**Q: What is Actuator?**
A: A set of production-ready endpoints that expose health, metrics, env, beans. Used by monitoring tools (Prometheus, Grafana). Secure in production — only expose `/health` publicly.

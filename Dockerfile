FROM maven:3.8.7-openjdk-18-slim as BUILD
COPY . /src
WORKDIR /src

RUN mvn install -DskipTests=true -Dcheckstyle.skip=true


FROM openjdk:22-ea-18-slim

WORKDIR /app

COPY --from=BUILD /src/target/*.jar /app.jar
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app.jar"]


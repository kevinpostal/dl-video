FROM elixir:1.20.4-otp-29-alpine AS build
RUN apk add --no-cache build-base git
ENV MIX_ENV=prod
WORKDIR /src
RUN mix local.hex --force && mix local.rebar --force
COPY mix.exs mix.lock ./
RUN mix deps.get --only prod && mix deps.compile
COPY config config
COPY lib lib
RUN mix release

# Same Alpine release as the builder image, so the release's ERTS links against matching libraries.
FROM alpine:3.24
RUN apk add --no-cache libstdc++ ncurses-libs openssl
WORKDIR /app
COPY --from=build /src/_build/prod/rel/bj_files /app
ENV HOME=/app
EXPOSE 4000
CMD ["/app/bin/bj_files", "start"]

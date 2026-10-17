FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends g++ libmbedtls-dev ca-certificates && rm -rf /var/lib/apt/lists/*
COPY . /source
# Copy the exact production source bytes; ONLY the public trust-header lookup
# is replaced by a conspicuously public test fixture. No production test switch.
RUN mkdir /native && cp /source/tqt_offline.cpp /source/tqt_offline.h /source/tqt_offline_wire.h /source/tqt_profile.h /native/ && \
    g++ -std=c++17 -Wall -Wextra -Werror -include /source/tests/native/compat.h \
      -I/source/tests/native/stubs -I/native \
      /source/tests/native/native_test.cpp /native/tqt_offline.cpp \
      -lmbedcrypto -o /native/offline-test
CMD ["/native/offline-test"]

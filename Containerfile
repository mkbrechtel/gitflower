# gitflower — package build, install test, and runtime image, all in one.
#
#   podman build -f Containerfile .                    # full pipeline → runtime image
#   podman build -f Containerfile --target=test .      # stop after the install smoke test
#   podman build -f Containerfile --target=build .     # just build the .deb + lintian
#
# The build stage runs the whole pytest suite (pybuild does that during
# dpkg-buildpackage); the test stage installs the produced .deb on a clean
# debian:trixie and exercises the installed package end to end.

FROM debian:trixie AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential debhelper dh-python pybuild-plugin-pyproject \
        python3-all python3-setuptools \
        python3-pytest python3-fastapi python3-click python3-pygit2 \
        python3-yaml python3-httpx git lintian \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src/gitflower
COPY . .
RUN dpkg-buildpackage -us -uc -b && lintian ../gitflower_*_all.deb
RUN mkdir /dist && cp ../gitflower_*_all.deb ../gitflower_*.buildinfo ../gitflower_*.changes /dist/


FROM debian:trixie AS test
RUN apt-get update
COPY --from=build /dist /dist
RUN apt-get install -y curl /dist/gitflower_*_all.deb && rm -rf /var/lib/apt/lists/*
COPY containertest/smoke.sh /smoke.sh
RUN sh /smoke.sh


FROM debian:trixie AS runtime
RUN apt-get update
COPY --from=build /dist /dist
RUN apt-get install -y /dist/gitflower_*_all.deb && rm -rf /var/lib/apt/lists/* /dist
# the test stage must have passed for this stage to be reachable
COPY --from=test /smoke.sh /usr/share/doc/gitflower/smoke.sh
RUN install -d -o gitflower -g gitflower /var/lib/gitflower /var/lib/gitflower/repos
USER gitflower
WORKDIR /var/lib/gitflower
EXPOSE 8747
CMD ["gitflower", "--config", "/etc/gitflower/config.yaml", "web", "--addr", ":8747"]

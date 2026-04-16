from __future__ import annotations

import logging

from relation_graph.desktop_worker import RelationGraphDesktopWorker


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    worker = RelationGraphDesktopWorker()
    return worker.run()


if __name__ == "__main__":
    raise SystemExit(main())

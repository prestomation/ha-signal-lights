# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/prestomation/ha-signal-lights/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|---------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| custom\_components/signal\_lights/\_\_init\_\_.py   |      108 |       80 |       32 |        0 |     20% |50, 55-62, 66-71, 75-78, 81-88, 91-93, 96-113, 119-129, 136-137, 143-167, 172-189 |
| custom\_components/signal\_lights/binary\_sensor.py |       24 |       24 |        2 |        0 |      0% |      7-55 |
| custom\_components/signal\_lights/config\_flow.py   |      235 |      235 |       94 |        0 |      0% |     8-709 |
| custom\_components/signal\_lights/const.py          |       11 |        0 |        0 |        0 |    100% |           |
| custom\_components/signal\_lights/coordinator.py    |      240 |      192 |       74 |        0 |     15% |21-22, 45-66, 70-80, 89-90, 94-117, 121-187, 195-198, 202, 208-210, 215-225, 233-309, 315-338, 345-355, 361-387, 398-416, 430-455, 471-477, 482-486, 490-493, 497-500, 504-505, 510, 514, 523-529, 534-540, 545 |
| custom\_components/signal\_lights/diagnostics.py    |       18 |        0 |        0 |        0 |    100% |           |
| custom\_components/signal\_lights/engine.py         |      195 |        8 |       74 |        6 |     95% |29, 40, 65, 72, 81, 90, 232, 237 |
| custom\_components/signal\_lights/sensor.py         |       55 |       55 |        8 |        0 |      0% |     9-116 |
| custom\_components/signal\_lights/services.py       |      270 |      232 |      106 |        0 |     10% |32-34, 39-44, 49-54, 193-224, 241-262, 274-288, 297-302, 307-640, 650-655 |
| custom\_components/signal\_lights/store.py          |      122 |       95 |       36 |        0 |     17% |53-56, 66-77, 81-124, 132, 140, 144-145, 149-156, 160-167, 175, 179-180, 185-193, 197-206, 210-217, 221-231, 235-236, 240-243, 251, 257-258 |
| custom\_components/signal\_lights/websocket.py      |       53 |       36 |       10 |        0 |     27% |18-19, 39-63, 82-84, 114-159 |
| **TOTAL**                                           | **1331** |  **957** |  **436** |    **6** | **25%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/prestomation/ha-signal-lights/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/prestomation/ha-signal-lights/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prestomation/ha-signal-lights/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/prestomation/ha-signal-lights/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fprestomation%2Fha-signal-lights%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/prestomation/ha-signal-lights/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.
# Operating AI Agents: Failure and Recovery
This is the repository for the LinkedIn Learning course `Operating AI Agents: Failure and Recovery`. The full course is available from [LinkedIn Learning][lil-course-url].

![course-name-alt-text][lil-thumbnail-url] 

## Course Description

As AI agents shift from experimentation to production, operational failures can create serious business risks. This intermediate course explores practical techniques for monitoring agent behavior, tracing execution paths, and identifying failure modes across single‑ and multi‑agent systems. Through hands-on GitHub Codespaces exercises, you learn how to implement rollback mechanisms, build automated recovery workflows, and create reports that surface agent health and system status in real time.
By the end of the course, you’ll have the skills to improve the safety and predictability of AI agents in production, and to respond quickly and effectively when failures occur.

## Notes
- This course, Operating AI Agents: Failure and Recovery, is the second course in the governing AI agents series. The first course is [Governing AI Agents: Visibility and Control](https://www.linkedin.com/learning/hands-on-ai-governing-ai-agents-in-practice).

## Requirements
- Python 3.9+
- An [OpenAI API key](https://platform.openai.com/account/api-keys)

## Setup

1. **Clone this repo** (or download the files).
2. **Create and activate a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate   # macOS/Linux
    venv\Scripts\activate      # Windows
    ```
3. **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4. **Set your OpenAI API key or place in .env file**:
    ```bash
    export OPENAI_API_KEY="your_api_key"      # macOS/Linux
    setx OPENAI_API_KEY "your_api_key"        # Windows PowerShell
    ```

## Instructor

Kesha Williams

Award-Winning Tech Innovator and AI/ML Leader

[lil-thumbnail-url]: https://media.licdn.com/dms/image/v2/D4D0DAQGtD_LN91IF3w/learning-public-crop_675_1200/B4DZwp3dwUIUAY-/0/1770228932378?e=2147483647&v=beta&t=VEsxitjglY8TpA7kMnUnVtUbng5reg1OKKMX_8m1CIY

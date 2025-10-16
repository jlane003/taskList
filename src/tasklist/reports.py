import shutil
import asciichartpy
from collections import Counter
from datetime import datetime, timedelta

# A simple list of common English "stop words" to exclude from keyword analysis.
STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "d", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have",
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's",
    "hers", "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself",
    "let's", "ll", "m", "me", "more", "most", "mustn't", "my", "myself", "no", "nor",
    "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "re", "s", "same", "shan't", "she", "she'd",
    "she'll", "she's", "should", "shouldn't", "so", "some", "such", "t", "than",
    "that", "that's", "the", "their", "theirs", "them", "themselves", "then",
    "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've",
    "this", "those", "through", "to", "too", "under", "until", "up", "ve", "very",
    "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
    "what", "what's", "when", "when's", "where", "where's", "which", "while",
    "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't",
    "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
    "yourselves"
}

# A very simple lexicon for sentiment analysis.
POSITIVE_WORDS = {"complete", "completed", "done", "finished", "good", "great", "success", "achieved"}
NEGATIVE_WORDS = {"bug", "error", "fail", "failed", "problem", "issue", "fix", "urgent"}


def get_terminal_width():
    """Returns the width of the terminal in characters."""
    return shutil.get_terminal_size().columns


def generate_bar_chart(data, title):
    """Generates a text-based bar chart."""
    width = get_terminal_width()
    max_label_len = max(len(label) for label in data)
    max_val = max(data.values())

    chart_width = width - max_label_len - 10  # Adjust for label, padding, and value
    if max_val == 0:
        scale = 0
    else:
        scale = chart_width / max_val

    output = f"\n--- {title} ---\n"
    for label, val in data.items():
        bar = "█" * int(val * scale)
        output += f"{label.rjust(max_label_len)} | {bar} {val}\n"
    return output


def get_top_keywords(cards, top_n=10):
    """Extracts the most common keywords from a list of card names."""
    words = []
    for card in cards:
        # Simple text cleaning
        cleaned_text = "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in card["name"])
        words.extend(
            word for word in cleaned_text.split() if word and word not in STOP_WORDS
        )

    return Counter(words).most_common(top_n)


def analyze_sentiment_by_week(cards):
    """Performs a simple sentiment analysis on cards, grouped by week."""
    weekly_sentiment = {}
    for card in cards:
        # Extract date from card ID
        timestamp = int(card["id"][:8], 16)
        card_date = datetime.fromtimestamp(timestamp)
        week_key = card_date.strftime("%Y-%U")  # Year-WeekNumber

        if week_key not in weekly_sentiment:
            weekly_sentiment[week_key] = {"score": 0, "count": 0}

        score = 0
        words = set(card["name"].lower().split())
        score += len(words.intersection(POSITIVE_WORDS))
        score -= len(words.intersection(NEGATIVE_WORDS))

        weekly_sentiment[week_key]["score"] += score
        weekly_sentiment[week_key]["count"] += 1

    # Calculate average sentiment
    avg_weekly_sentiment = {}
    for week, data in weekly_sentiment.items():
        avg_score = data["score"] / data["count"]
        if avg_score > 0.2:
            sentiment = "Positive"
        elif avg_score < -0.2:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
        avg_weekly_sentiment[week] = sentiment

    return avg_weekly_sentiment


def generate_activity_chart(actions, done_list_name="done"):
    """Generates a text-based line chart for task activity."""
    creations = Counter()
    completions = Counter()

    for action in actions:
        action_date = datetime.fromisoformat(action["date"].replace("Z", "+00:00")).date()
        if action["type"] == "createCard":
            creations[action_date] += 1
        elif action["type"] == "updateCard":
            if action.get("data", {}).get("listAfter", {}).get("name", "").lower() == done_list_name.lower():
                completions[action_date] += 1

    all_dates = sorted(set(creations.keys()) | set(completions.keys()))
    if not all_dates:
        return "No activity to report."

    if len(all_dates) < 2:
        return "Not enough data to generate an activity chart."

    # Create a full date range
    date_range = []
    current_date = all_dates[0]
    while current_date <= all_dates[-1]:
        date_range.append(current_date)
        current_date += timedelta(days=1)

    created_counts = [creations.get(date, 0) for date in date_range]
    completed_counts = [completions.get(date, 0) for date in date_range]

    output = "\n--- Task Activity Over Time ---\n"
    output += "\n--- Tasks Created ---\n"
    output += asciichartpy.plot(created_counts, {"height": 10})
    output += "\n\n--- Tasks Completed ---\n"
    output += asciichartpy.plot(completed_counts, {"height": 10})

    return output

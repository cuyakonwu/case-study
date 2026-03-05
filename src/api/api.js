
export const getAIMessage = async (userQuery) => {
  try {
    const response = await fetch("http://localhost:8000/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message: userQuery }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return {
      role: "assistant",
      content: data.reply,
      suggested_parts: data.suggested_parts || []
    };
  } catch (error) {
    console.error("Error fetching AI message:", error);
    return {
      role: "assistant",
      content: "Sorry, I am having trouble connecting to the server.",
      suggested_parts: []
    };
  }
};

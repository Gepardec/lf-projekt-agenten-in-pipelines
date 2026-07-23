---
safe-outputs:
  jobs:
    google-chat-notify:
      description: "Send a message to Google Chat"
      runs-on: ubuntu-latest
      output: "Message sent to Google Chat!"
      inputs:
        message:
          description: "The message to send"
          required: true
          type: string
      steps:
        - name: Send Google Chat message
          env:
            GOOGLE_CHAT_WEBHOOK: "${{ secrets.GOOGLE_CHAT_WEBHOOK }}"
          run: |
            if [ -f "$GH_AW_AGENT_OUTPUT" ]; then
              MESSAGE=$(cat "$GH_AW_AGENT_OUTPUT" | jq -r '.items[] | select(.type == "google_chat_notify") | .message')
              # Use jq to safely escape JSON content
              PAYLOAD=$(jq -n --arg text "$MESSAGE" '{text: $text}')
              curl -X POST "$GOOGLE_CHAT_WEBHOOK" \
                -H 'Content-Type: application/json; charset=UTF-8' \
                -d "$PAYLOAD"
            else
              echo "No agent output found"
              exit 1
            fi
---